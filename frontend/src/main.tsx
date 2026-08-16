import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { EventType, PublicClientApplication, type AccountInfo } from "@azure/msal-browser"
import { MsalProvider } from "@azure/msal-react"

import "./index.css"
import App from "./App.tsx"
import { msalConfig } from "./authConfig"

const msalInstance = new PublicClientApplication(msalConfig)

// msal-browser v3+ requires an explicit initialize() before any other
// call (including getAllAccounts()) — render only starts once that
// resolves.
void msalInstance.initialize().then(() => {
  const existing = msalInstance.getAllAccounts()
  if (existing.length > 0) {
    msalInstance.setActiveAccount(existing[0])
  }

  // Keep "the" active account in sync with whichever one just signed in —
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

  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <MsalProvider instance={msalInstance}>
        <App />
      </MsalProvider>
    </StrictMode>,
  )
})
