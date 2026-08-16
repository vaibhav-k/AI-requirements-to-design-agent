/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Entra ID tenant id for the frontend's own SPA app registration. */
  readonly VITE_ENTRA_TENANT_ID?: string
  /** Client id of the frontend's own SPA app registration (not the API's). */
  readonly VITE_ENTRA_CLIENT_ID?: string
  /** The API's exposed scope, e.g. api://<api-client-id>/access_as_user. */
  readonly VITE_API_SCOPE?: string
  /** Base URL of the FastAPI backend. Defaults to http://localhost:8000. */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
