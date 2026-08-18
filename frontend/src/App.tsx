import { useState } from "react"
import { BrowserAuthError } from "@azure/msal-browser"
import { useIsAuthenticated, useMsal } from "@azure/msal-react"

import "./App.css"
import { authIsConfigured, loginRequest } from "./authConfig"
import { ErrorBanner } from "./components/ErrorBanner"
import { Sidebar } from "./components/Sidebar"
import { Workspace } from "./components/Workspace"

type View = { name: "new" } | { name: "session"; sessionId: string }

/** Turns a `loginPopup`/`logoutPopup` rejection into text a non-technical
 * user can act on. `loginPopup` previously had no `.catch` at all — any
 * failure (a stuck `interaction_in_progress` flag from an earlier attempt,
 * a browser-blocked popup, an app-registration redirect URI mismatch that
 * leaves the popup unable to complete and eventually `timed_out`) was an
 * unhandled promise rejection: nothing changed on screen, and the only way
 * to find out anything had gone wrong was to open the browser console. */
function describeSignInError(err: unknown): string {
  if (err instanceof BrowserAuthError) {
    if (err.errorCode === "interaction_in_progress") {
      return (
        "A previous sign-in attempt is still marked as in progress in this " +
        "browser tab. Reload the page and try again — if it keeps happening, " +
        "clear this site's session storage."
      )
    }
    if (err.errorCode === "timed_out") {
      return (
        "The sign-in popup didn't complete in time. Check whether your " +
        "browser blocked the popup, or whether the app's registered " +
        "redirect URI matches this page's actual address."
      )
    }
    if (err.errorCode === "popup_window_error" || err.errorCode === "user_cancelled") {
      return "The sign-in popup was closed or blocked before finishing. Try again."
    }
  }
  return err instanceof Error ? err.message : String(err)
}

function AuthBar() {
  const { instance, accounts } = useMsal()
  const isAuthenticated = useIsAuthenticated()
  const [error, setError] = useState<string | null>(null)

  if (!authIsConfigured) {
    return <span className="muted">Sign-in not configured — running anonymously.</span>
  }

  if (isAuthenticated) {
    return (
      <span>
        Signed in as {accounts[0]?.username ?? accounts[0]?.name ?? "unknown"}{" "}
        <button
          type="button"
          onClick={() => {
            setError(null)
            instance.logoutPopup().catch((err: unknown) => setError(describeSignInError(err)))
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
          instance.loginPopup(loginRequest).catch((err: unknown) => setError(describeSignInError(err)))
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
            instance.loginPopup(loginRequest).catch((err: unknown) => setError(describeSignInError(err)))
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
