import { useState } from "react"
import { BrowserAuthError } from "@azure/msal-browser"
import { useIsAuthenticated, useMsal } from "@azure/msal-react"

import "./App.css"
import { authIsConfigured, loginRequest } from "./authConfig"
import { ErrorBanner } from "./components/ErrorBanner"
import { Sidebar } from "./components/Sidebar"
import { Workspace } from "./components/Workspace"
import { useCurrentUser } from "./useCurrentUser"

type View = { name: "new" } | { name: "session"; sessionId: string }

/** Turns a `loginRedirect`/`logoutRedirect` rejection into text a
 * non-technical user can act on. These previously had no `.catch` at all
 * — any failure was an unhandled promise rejection: nothing changed on
 * screen, and the only way to find out anything had gone wrong was to
 * open the browser console.
 *
 * Sign-in uses a full-page redirect rather than a popup: this app hit a
 * string of popup-specific failures in practice (`interaction_in_progress`,
 * `timed_out`, `block_nested_popups`, and — worse — the popup silently
 * loading this app's own UI instead of completing the auth handshake at
 * all, MSAL's popup-completion detection never firing even though the
 * popup reached the correct redirect URI with a valid response). That
 * class of failure is specific to popup/opener communication, which some
 * managed-browser environments (enterprise policies, tracking-protection
 * features) interfere with. A redirect navigates the whole tab instead of
 * opening a second window, so none of that machinery is involved. */
function describeSignInError(err: unknown): string {
  if (err instanceof BrowserAuthError && err.errorCode === "interaction_in_progress") {
    return (
      "A previous sign-in attempt is still marked as in progress in this " +
      "browser tab. Reload the page and try again — if it keeps happening, " +
      "clear this site's session storage."
    )
  }
  return err instanceof Error ? err.message : String(err)
}

/** The signed-in caller's Entra ID App Roles (`GET /me`, see
 * `useCurrentUser.ts`), shown next to "Signed in as ..." so it's visible
 * without having to guess from which buttons happen to be greyed out — the
 * same roles `permissions.ts`'s `hasAnyRole` checks against everywhere
 * else in this app. Renders nothing until `/me` has actually resolved
 * (`loaded`), and nothing at all if the caller holds no role (an
 * authenticated-but-unassigned caller — every request will 403; that's
 * surfaced by the actions themselves, not duplicated here). */
function RoleBadge() {
  const { roles, loaded } = useCurrentUser()
  if (!loaded || roles.length === 0) return null
  return <span className="role-badge" title="Your Entra ID App Roles">{roles.join(", ")}</span>
}

function AuthBar() {
  const { instance, accounts } = useMsal()
  const isAuthenticated = useIsAuthenticated()
  const [error, setError] = useState<string | null>(null)

  if (!authIsConfigured) {
    return (
      <span className="muted">
        Sign-in not configured — running anonymously. <RoleBadge />
      </span>
    )
  }

  if (isAuthenticated) {
    return (
      <span>
        Signed in as {accounts[0]?.username ?? accounts[0]?.name ?? "unknown"} <RoleBadge />{" "}
        <button
          type="button"
          onClick={() => {
            setError(null)
            instance.logoutRedirect().catch((err: unknown) => setError(describeSignInError(err)))
          }}
        >
          Sign out
        </button>
        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      </span>
    )
  }

  return (
    <span>
      <button
        type="button"
        onClick={() => {
          setError(null)
          instance.loginRedirect(loginRequest).catch((err: unknown) => setError(describeSignInError(err)))
        }}
      >
        Sign in
      </button>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
    </span>
  )
}

function Gate({ children }: { children: React.ReactNode }) {
  const { instance } = useMsal()
  const isAuthenticated = useIsAuthenticated()
  const [anonymous, setAnonymous] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Three ways in: signed in via Entra, sign-in not configured yet (so
  // anonymous is the only option — matches the backend's AUTH_ENABLED=false
  // default), or the user explicitly chose to skip signing in against a
  // backend that also has auth disabled.
  if (isAuthenticated || anonymous || !authIsConfigured) {
    return <>{children}</>
  }

  return (
    <div className="gate">
      <h1>Requirements → System Design Agent</h1>
      <p>Sign in to see and manage your own sessions.</p>
      <div className="button-row">
        <button
          type="button"
          onClick={() => {
            setError(null)
            instance.loginRedirect(loginRequest).catch((err: unknown) => setError(describeSignInError(err)))
          }}
        >
          Sign in
        </button>
        <button type="button" onClick={() => setAnonymous(true)}>
          Continue without signing in
        </button>
      </div>
      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
      <p className="muted">
        "Continue without signing in" only works against a backend running with{" "}
        <code>AUTH_ENABLED=false</code> — otherwise every request gets a 401.
      </p>
    </div>
  )
}

export default function App() {
  const [view, setView] = useState<View>({ name: "new" })
  const [sidebarRefreshKey, setSidebarRefreshKey] = useState(0)

  return (
    <div className="app">
      <header className="app-header">
        <h1>Requirements → System Design Agent</h1>
        <AuthBar />
      </header>

      <main className="app-main">
        <Gate>
          <Sidebar
            activeSessionId={view.name === "session" ? view.sessionId : null}
            onSelect={(sessionId) => setView({ name: "session", sessionId })}
            onStartNew={() => setView({ name: "new" })}
            refreshKey={sidebarRefreshKey}
          />
          <Workspace
            sessionId={view.name === "session" ? view.sessionId : null}
            onSessionCreated={(sessionId) => {
              setSidebarRefreshKey((key) => key + 1)
              setView({ name: "session", sessionId })
            }}
          />
        </Gate>
      </main>
    </div>
  )
}
