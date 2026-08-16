import { useEffect, useState } from "react"

import { ApiError, useRequirementsApi } from "../api"
import type { RequirementsRunView } from "../types"
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

/** Session list, refactored from the original standalone `SessionList` view
 * into a persistent left rail so switching sessions doesn't leave the
 * conversation/artifact workspace. Purely a read of `GET /requirements-runs`
 * — no client-side session state is invented here. */
export function Sidebar({ activeSessionId, onSelect, onStartNew, refreshKey }: SidebarProps) {
  const api = useRequirementsApi()
  const [runs, setRuns] = useState<RequirementsRunView[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setError(null)
    api
      .listRuns()
      .then((result) => {
        if (!cancelled) setRuns(result)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setRuns([])
        setError(err instanceof ApiError ? err.message : "Could not load sessions.")
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey, api])

  return (
    <aside className="sidebar">
      <button type="button" className="new-session-button" onClick={onStartNew}>
        + New session
      </button>

      {error && <ErrorBanner message={error} />}

      {runs === null && <p className="muted">Loading…</p>}

      {runs !== null && runs.length === 0 && !error && (
        <p className="muted">No sessions yet.</p>
      )}

      {runs !== null && runs.length > 0 && (
        <ul className="session-list">
          {runs.map((run) => (
            <li key={run.session_id}>
              <button
                type="button"
                className={
                  run.session_id === activeSessionId ? "session-item active" : "session-item"
                }
                onClick={() => onSelect(run.session_id)}
              >
                <code>{run.session_id.slice(0, 8)}</code>
                <span className="muted">{run.stage}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  )
}
