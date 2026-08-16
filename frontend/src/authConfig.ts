import type { Configuration } from "@azure/msal-browser"

// Read once at module load. All three must be set for sign-in to work —
// see the "Frontend: Entra ID App Registration" section of the README for
// how to get them (a *second*, SPA-platform app registration, separate
// from the API's own client id: an SPA can't hold a client secret the way
// a confidential client can, so it needs its own registration either way).
const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID as string | undefined
const clientId = import.meta.env.VITE_ENTRA_CLIENT_ID as string | undefined
const apiScope = import.meta.env.VITE_API_SCOPE as string | undefined

export const authIsConfigured = Boolean(tenantId && clientId && apiScope)

if (!authIsConfigured) {
  // Not a hard failure: the app still renders and can be used against a
  // backend running with AUTH_ENABLED=false (anonymous/local dev) without
  // signing in at all — see App.tsx's "Continue without signing in" path.
  // eslint-disable-next-line no-console
  console.warn(
    "frontend/.env is missing VITE_ENTRA_TENANT_ID / VITE_ENTRA_CLIENT_ID / " +
      "VITE_API_SCOPE — sign-in is disabled until it's configured. See the " +
      "README's Entra ID App Registration section.",
  )
}

export const msalConfig: Configuration = {
  auth: {
    clientId: clientId ?? "",
    authority: `https://login.microsoftonline.com/${tenantId ?? "common"}`,
    redirectUri: "/",
  },
  cache: {
    // sessionStorage, not localStorage: tokens shouldn't outlive the tab,
    // and MSAL's own guidance prefers it for SPAs unless SSO across tabs
    // is specifically needed.
    cacheLocation: "sessionStorage",
  },
}

export const loginRequest = {
  scopes: apiScope ? [apiScope] : [],
}

export const apiBaseUrl =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://localhost:8000"
