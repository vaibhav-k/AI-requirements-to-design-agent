import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { EventType, PublicClientApplication, type AccountInfo } from "@azure/msal-browser"
import { MsalProvider } from "@azure/msal-react"

import "./index.css"
import App from "./App.tsx"
import { msalConfig } from "./authConfig"

const msalInstance = new PublicClientApplication(msalConfig)

function renderApp() {
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <App />
      </MsalProvider>
    </StrictMode>,
  )
}

// msal-browser v3+ requires an explicit initialize() before any other
// call (including getAllAccounts()) - render only starts once that
// resolves. handleRedirectPromise() then completes the sign-in that
// App.tsx's loginRedirect() started: on the page load right after Entra
// ID redirects back here, it exchanges the code in the URL for tokens and
// returns the result; on every other page load it resolves to `null`
// almost immediately, so it's safe (and necessary) to always call.
//
// Sign-in uses a redirect rather than a popup specifically because the
// popup flow proved unreliable in practice here - see App.tsx's
// `describeSignInError` for the failure history.
void msalInstance
  .initialize()
  .then(() => msalInstance.handleRedirectPromise())
  .then((result) => {
    if (result?.account) {
      msalInstance.setActiveAccount(result.account)
    } else if (!msalInstance.getActiveAccount()) {
      const existing = msalInstance.getAllAccounts()
      if (existing.length > 0) {
        msalInstance.setActiveAccount(existing[0])
      }
    }

    // Keep "the" active account in sync with whichever one just signed in -
    // useMsal()'s `accounts` (and therefore useRequirementsApi's token
    // acquisition) reads whatever MSAL considers active.
    msalInstance.addEventCallback((event) => {
      if (event.eventType === EventType.LOGIN_SUCCESS && event.payload) {
        const account = (event.payload as { account?: AccountInfo }).account
        if (account) {
          msalInstance.setActiveAccount(account)
        }
      }
    })

    renderApp()
  })
  .catch((error: unknown) => {
    // A failed handleRedirectPromise() (e.g. the redirect carried an error
    // response instead of a code) must not leave the user on a blank page
    // forever - render the app anyway so the Gate's Sign in button is
    // still reachable to retry.
    // eslint-disable-next-line no-console
    console.error("MSAL redirect handling failed", error)
    renderApp()
  })
