import { useEffect, useState } from "react"

import { describeError, useRequirementsApi } from "../api"
import { hasAnyRole, ROLE_ADMIN, ROLE_ARCHITECT, ROLE_REVIEWER, ROLE_USER } from "../permissions"
import type { RequirementsRunView } from "../types"
import { useCurrentUser } from "../useCurrentUser"
import { useResizableWidth } from "../useResizableWidth"
import { ErrorBanner } from "./ErrorBanner"

interface SidebarProps {
  activeSessionId: string | null
  onSelect: (sessionId: string) => void
  onStartNew: () => void
  /** Bumped by the parent whenever a session list change is known to have
   * happened (a new session was created), to force a refetch without this
   * component needing to know why. */
  refreshKey: number
}

/** Display label for a session in the list: its own name once renamed,
 * otherwise a shortened id - same fallback the list used before renaming
 * existed, kept so a never-renamed session still reads as identifiable. */
function displayName(run: RequirementsRunView): string {
  return run.name ?? run.session_id.slice(0, 8)
}

/** One row in the sessions list - its own component so the inline rename
 * text field can hold its own "currently editing" state without that
 * leaking into the list-wide `runs` state Sidebar already manages. */
function SessionRow({
  run,
  isActive,
  onSelect,
  renameAllowed,
  renameDisabledReason,
  showOwner,
  onRename,
}: {
  run: RequirementsRunView
  isActive: boolean
  onSelect: () => void
  renameAllowed: boolean
  renameDisabledReason?: string
  /** Whether to show `run.owner_name` under the session's label - only
   * meaningful for an Admin browsing every session (see `Sidebar`'s
   * `isAdmin`); for anyone else every session shown is already their own. */
  showOwner: boolean
  onRename: (name: string) => Promise<void>
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(displayName(run))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const beginEditing = () => {
    setDraft(run.name ?? "")
    setError(null)
    setEditing(true)
  }

  const commit = () => {
    const trimmed = draft.trim()
    if (!trimmed || trimmed === (run.name ?? "")) {
      setEditing(false)
      return
    }
    setSaving(true)
    onRename(trimmed)
      .then(() => setEditing(false))
      .catch((err: unknown) => setError(describeError(err)))
      .finally(() => setSaving(false))
  }

  if (editing) {
    return (
      <li>
        <div className="session-item session-item-editing">
          <input
            autoFocus
            className="session-rename-input"
            value={draft}
            disabled={saving}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") commit()
              if (event.key === "Escape") setEditing(false)
            }}
            onBlur={commit}
            maxLength={200}
          />
          {error && <span className="session-rename-error">{error}</span>}
        </div>
      </li>
    )
  }

  return (
    <li>
      <div className={isActive ? "session-item active" : "session-item"}>
        <button type="button" className="session-item-select" onClick={onSelect}>
          <span className="session-item-name">{displayName(run)}</span>
          <span className="muted">
            {run.stage}
            {/* Admin's cross-user view always names who started a session -
             * `run.owner_name` is only ever unset for a session created
             * before ownership tracking existed (or while AUTH_ENABLED was
             * off), which has no owner to report; labeling it explicitly
             * avoids that reading as a bug in this display. */}
            {showOwner && ` - ${run.owner_name ?? "unowned"}`}
          </span>
        </button>
        <button
          type="button"
          className="session-rename-button"
          onClick={beginEditing}
          disabled={!renameAllowed}
          title={renameAllowed ? "Rename session" : renameDisabledReason}
          aria-label="Rename session"
        >
          ✎
        </button>
      </div>
    </li>
  )
}

/** Session list, refactored from the original standalone `SessionList` view
 * into a persistent left rail so switching sessions doesn't leave the
 * conversation/artifact workspace. Purely a read of `GET /requirements-runs`
 * - no client-side session state is invented here, aside from the pane's
 * own width/collapsed UI state (see `useResizableWidth` and `collapsed`
 * below), which is presentation only and never sent to the backend.
 */
export function Sidebar({ activeSessionId, onSelect, onStartNew, refreshKey }: SidebarProps) {
  const api = useRequirementsApi()
  const [runs, setRuns] = useState<RequirementsRunView[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState<boolean>(
    () => typeof window !== "undefined" && window.localStorage.getItem("sidebar-collapsed") === "1",
  )
  const { width, startDrag } = useResizableWidth({
    defaultWidth: 220,
    min: 160,
    max: 480,
    storageKey: "sidebar-width",
  })

  const { roles, loaded: rolesLoaded } = useCurrentUser()
  // Same "any functional role can act on what they own" shape the backend
  // enforces for rename (see app/api/routes/requirements.py's rename_run
  // and the README's RBAC section) - defaults to allowed while roles
  // haven't loaded yet, matching every other role gate in this app.
  const renameAllowed = !rolesLoaded || hasAnyRole(roles, [ROLE_USER, ROLE_ARCHITECT, ROLE_REVIEWER])
  const isAdmin = rolesLoaded && roles.includes(ROLE_ADMIN)

  useEffect(() => {
    window.localStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0")
  }, [collapsed])

  // Polls `GET /requirements-runs` every few seconds so a session's stage
  // (e.g. "generating" → "architecture" once an accept/refine-architecture
  // call another tab - or another user entirely, for an Admin - kicked off
  // finishes) shows up here without the person having to switch away and
  // back or start a new session to force `refreshKey` to bump. `refreshKey`
  // still triggers an immediate refetch on top of the interval (e.g. right
  // after this tab itself starts a session), so the list never waits out a
  // full poll interval for a change this tab caused itself.
  const POLL_INTERVAL_MS = 5000
  useEffect(() => {
    let cancelled = false
    let isFirstLoad = true

    const fetchRuns = () => {
      api
        .listRuns()
        .then((result) => {
          if (!cancelled) {
            setRuns(result)
            setError(null)
          }
        })
        .catch((err: unknown) => {
          if (cancelled) return
          // Only wipe the list to "empty" on the very first load, when
          // there's nothing on screen to preserve - a poll that fails later
          // (a transient network blip) surfaces the error but leaves
          // whatever was already showing alone, rather than flashing to
          // "No sessions yet." every few seconds during an outage.
          if (isFirstLoad) setRuns([])
          setError(`Could not load sessions: ${describeError(err)}`)
        })
        .finally(() => {
          isFirstLoad = false
        })
    }

    fetchRuns()
    const intervalId = window.setInterval(fetchRuns, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      window.clearInterval(intervalId)
    }
  }, [refreshKey, api])

  const handleRename = (sessionId: string, name: string) =>
    api.renameRun(sessionId, name).then((updated) => {
      setRuns((current) =>
        current ? current.map((run) => (run.session_id === sessionId ? updated : run)) : current,
      )
    })

  if (collapsed) {
    return (
      <aside className="sidebar sidebar-collapsed">
        <button
          type="button"
          className="sidebar-collapse-toggle"
          onClick={() => setCollapsed(false)}
          title="Expand sessions pane"
          aria-label="Expand sessions pane"
        >
          »
        </button>
      </aside>
    )
  }

  return (
    <div className="sidebar-wrapper" style={{ width }}>
      <aside className="sidebar">
        <div className="sidebar-header">
          <button type="button" className="new-session-button" onClick={onStartNew}>
            + New session
          </button>
          <button
            type="button"
            className="sidebar-collapse-toggle"
            onClick={() => setCollapsed(true)}
            title="Collapse sessions pane"
            aria-label="Collapse sessions pane"
          >
            «
          </button>
        </div>

        {error && <ErrorBanner message={error} />}

        {runs === null && <p className="muted">Loading…</p>}

        {runs !== null && runs.length === 0 && !error && (
          <p className="muted">No sessions yet.</p>
        )}

        {runs !== null && runs.length > 0 && (
          <ul className="session-list">
            {runs.map((run) => (
              <SessionRow
                key={run.session_id}
                run={run}
                isActive={run.session_id === activeSessionId}
                onSelect={() => onSelect(run.session_id)}
                renameAllowed={renameAllowed}
                renameDisabledReason="Requires the User, Architect, or Reviewer role."
                showOwner={isAdmin}
                onRename={(name) => handleRename(run.session_id, name)}
              />
            ))}
          </ul>
        )}
      </aside>
      <div
        className="resize-handle"
        onMouseDown={startDrag}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize sessions pane"
      />
    </div>
  )
}
