import { useState } from "react"
import { useIsAuthenticated, useMsal } from "@azure/msal-react"

import "./App.css"
import { authIsConfigured, loginRequest } from "./authConfig"
import { Sidebar } from "./components/Sidebar"
import { Workspace } from "./components/Workspace"

type View = { name: "new" } | { name: "session"; sessionId: string }

function AuthBar() {
  const { instance, accounts } = useMsal()
  const isAuthenticated = useIsAuthenticated()

  if (!authIsConfigured) {
    return <span className="muted">Sign-in not configured — running anonymously.</span>
  }

  if (isAuthenticated) {
    return (
      <span>
        Signed in as {accounts[0]?.username ?? accounts[0]?.name ?? "unknown"}{" "}
        <button type="button" onClick={() => void instance.logoutPopup()}>
          Sign out
        </button>
      </span>
    )
  }

  return (
    <button type="button" onClick={() => void instance.loginPopup(loginRequest)}>
      Sign in
    </button>
  )
}

function Gate({ children }: { children: React.ReactNode }) {
  const { instance } = useMsal()
  const isAuthenticated = useIsAuthenticated()
  const [anonymous, setAnonymous] = useState(false)

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
        <button type="button" onClick={() => void instance.loginPopup(loginRequest)}>
          Sign in
        </button>
        <button type="button" onClick={() => setAnonymous(true)}>
          Continue without signing in
        </button>
      </div>
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
