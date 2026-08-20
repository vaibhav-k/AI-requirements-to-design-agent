import { useCallback, useMemo } from "react"
import { InteractionRequiredAuthError, type IPublicClientApplication } from "@azure/msal-browser"
import { useMsal } from "@azure/msal-react"

import { apiBaseUrl, authIsConfigured, loginRequest } from "./authConfig"
import type {
  ManualRequirementsRequest,
  MeResponse,
  RequirementsArtifact,
  RequirementsRunView,
  SystemDesignArtifact,
  WorkBreakdownArtifact,
} from "./types"

/** Thrown for any non-2xx response, carrying the backend's `detail` message
 * (FastAPI's standard error body shape) when it has one. */
export class ApiError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = "ApiError"
    this.status = status
  }
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof (body as { detail: unknown }).detail === "string"
    ) {
      return (body as { detail: string }).detail
    }
  } catch {
    // Response body wasn't JSON (or was empty) - fall through to the
    // generic message below rather than let this throw mask the real error.
  }
  return `Request failed with status ${response.status}`
}

/** Thrown when acquiring a sign-in token itself fails - distinct from
 * ApiError (a backend response) and from a network failure (the request
 * never reached the backend at all), so the UI can say exactly which of
 * the three happened instead of one ambiguous "could not load" message. */
export class TokenAcquisitionError extends Error {
  constructor(cause: unknown) {
    const detail = cause instanceof Error ? cause.message : String(cause)
    super(`Could not acquire a sign-in token: ${detail}`)
    this.name = "TokenAcquisitionError"
  }
}

async function acquireToken(
  instance: IPublicClientApplication,
  account: ReturnType<IPublicClientApplication["getAllAccounts"]>[number] | undefined,
): Promise<string | null> {
  if (!authIsConfigured || !account) {
    // Matches app/security/auth.py's require_user: no token is only a
    // problem if the backend has AUTH_ENABLED=true. Sending the request
    // without an Authorization header lets that backend reject it with its
    // own "Missing bearer token." 401 rather than the frontend guessing.
    return null
  }
  const request = { ...loginRequest, account }
  try {
    const result = await instance.acquireTokenSilent(request)
    return result.accessToken
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      try {
        const result = await instance.acquireTokenPopup(request)
        return result.accessToken
      } catch (popupError) {
        throw new TokenAcquisitionError(popupError)
      }
    }
    throw new TokenAcquisitionError(error)
  }
}

/** Thrown when `fetch` itself fails - the request never reached the
 * backend (DNS/CORS/connection-refused/offline) - so this is never
 * confused with an ApiError (a real HTTP response the backend sent). */
export class NetworkError extends Error {
  constructor(path: string, cause: unknown) {
    const detail = cause instanceof Error ? cause.message : String(cause)
    super(`Could not reach the server at ${path}: ${detail}`)
    this.name = "NetworkError"
  }
}

/** A human-readable description of any error a request can throw -
 * ApiError, NetworkError, and TokenAcquisitionError all already carry a
 * specific, self-explanatory `message` (see above); this only exists so
 * callers never fall back to a made-up generic string that hides which of
 * the three actually happened (or masks a genuinely unexpected error type). */
export function describeError(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

/** Turns a caught error into transcript/error-banner text - an `ApiError`
 * with status 401 ("not authenticated at all") or 403 ("authenticated, but
 * missing the role this needs") gets a message that says so in plain
 * language rather than surfacing the raw backend detail as the *only*
 * signal; 403's backend detail is already specific about which role is
 * missing (see `require_role` in app/security/auth.py), so it's appended
 * rather than replaced. Any other status, or a non-ApiError, falls back to
 * `fallback`. Shared by Workspace.tsx and any other component that surfaces
 * a mutating call's failure directly (e.g. RequirementsEditor.tsx). */
export function friendlyErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return `You're not signed in. Sign in above and try again. (${err.message})`
    }
    if (err.status === 403) {
      return `You don't have permission to do this: ${err.message}`
    }
    return err.message
  }
  return fallback
}

/** Typed client for the `/requirements-runs` endpoints (app/api/routes/requirements.py).
 *
 * A hook, not a plain module, because acquiring a token needs the active
 * MSAL account - `useMsal()` is the only supported way to reach that
 * outside a class component.
 */
export function useRequirementsApi() {
  const { instance, accounts } = useMsal()

  const fetchWithAuth = useCallback(
    async (path: string, init: RequestInit = {}): Promise<Response> => {
      const token = await acquireToken(instance, accounts[0])
      const headers = new Headers(init.headers)
      // Multipart bodies (file uploads) must NOT get an explicit
      // Content-Type here - the browser sets one itself, including the
      // random boundary string the server needs to parse the body. Setting
      // "application/json" (or anything else) on a FormData body breaks
      // multipart parsing on the server.
      if (init.body && !(init.body instanceof FormData)) {
        headers.set("Content-Type", "application/json")
      }
      if (token) {
        headers.set("Authorization", `Bearer ${token}`)
      }
      try {
        return await fetch(`${apiBaseUrl}${path}`, { ...init, headers })
      } catch (error) {
        // fetch() rejects (rather than resolving with a non-ok Response)
        // only when the request never reached the server at all - refused
        // connection, DNS failure, CORS block, offline. Wrapping it here
        // means callers never have to guess whether a caught error came
        // from the backend or from never reaching it.
        throw new NetworkError(path, error)
      }
    },
    [instance, accounts],
  )

  const request = useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      const response = await fetchWithAuth(path, init)
      if (!response.ok) {
        throw new ApiError(await readErrorDetail(response), response.status)
      }
      if (response.status === 204) {
        return undefined as T
      }
      return (await response.json()) as T
    },
    [fetchWithAuth],
  )

  /** Like `request`, but for endpoints returning a body that isn't JSON -
   * only the diagram SVG endpoint today (`app/api/routes/artifacts.py`'s
   * `get_architecture_diagram` returns `image/svg+xml`, not `application/json`). */
  const requestText = useCallback(
    async (path: string): Promise<string> => {
      const response = await fetchWithAuth(path)
      if (!response.ok) {
        throw new ApiError(await readErrorDetail(response), response.status)
      }
      return response.text()
    },
    [fetchWithAuth],
  )

  /** Triggers a browser download of a same-origin-authenticated response
   * body - used only by `exportWorkBreakdownCsv` today, since that's the
   * one endpoint in this app that returns a file rather than JSON/SVG text
   * (`app/api/routes/work_breakdown.py`'s `export_work_breakdown`, which
   * needs the same bearer token as every other request here, so a plain
   * `<a href="...">` pointed straight at the backend URL isn't an option).
   * Fetches the blob through the same `fetchWithAuth` every other request
   * uses, then drives a temporary, invisible `<a download>` through an
   * object URL - the standard way to save a fetched blob without
   * navigating the page away. */
  const downloadFile = useCallback(
    async (path: string, filename: string): Promise<void> => {
      const response = await fetchWithAuth(path)
      if (!response.ok) {
        throw new ApiError(await readErrorDetail(response), response.status)
      }
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      try {
        const link = document.createElement("a")
        link.href = url
        link.download = filename
        document.body.appendChild(link)
        link.click()
        link.remove()
      } finally {
        URL.revokeObjectURL(url)
      }
    },
    [fetchWithAuth],
  )

  // Memoized so the returned object (and each method on it) is stable
  // across renders as long as `request`/`requestText` are (which are
  // themselves stable unless the active MSAL account changes) - lets
  // callers safely list e.g. `api.listRuns` in a `useEffect` dependency
  // array instead of needing to suppress the exhaustive-deps warning.
  return useMemo(
    () => ({
      /** The caller's identity + Entra ID App Roles (`app/web/main.py`'s
       * `whoami`) - used by `useCurrentUser` to grey out actions the
       * signed-in user's role doesn't permit. Works in every auth mode,
       * including anonymous (`AUTH_ENABLED=false`), since `/me` never
       * 401s in that mode. */
      getMe: () => request<MeResponse>("/me"),

      listRuns: () => request<RequirementsRunView[]>("/requirements-runs"),

      startRun: (input: string) =>
        request<RequirementsRunView>("/requirements-runs", {
          method: "POST",
          body: JSON.stringify({ input }),
        }),

      startRunFromUpload: (file: File, notes?: string) => {
        const form = new FormData()
        form.set("file", file)
        if (notes) {
          form.set("notes", notes)
        }
        return request<RequirementsRunView>("/requirements-runs/upload", {
          method: "POST",
          body: form,
        })
      },

      getRun: (sessionId: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}`),

      /** Set a session's display label - `app/api/routes/requirements.py`'s
       * `rename_run`. Open to any of User/Architect/Reviewer on their own
       * sessions (Admin on any session); see permissions.ts's
       * `hasAnyRole`/`ROLE_*` for how the UI grey out mirrors that. */
      renameRun: (sessionId: string, name: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/rename`, {
          method: "POST",
          body: JSON.stringify({ name }),
        }),

      refineRun: (sessionId: string, input: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/refine`, {
          method: "POST",
          body: JSON.stringify({ input }),
        }),

      refineRunFromUpload: (sessionId: string, file: File, notes?: string) => {
        const form = new FormData()
        form.set("file", file)
        if (notes) {
          form.set("notes", notes)
        }
        return request<RequirementsRunView>(
          `/requirements-runs/${sessionId}/refine/upload`,
          {
            method: "POST",
            body: form,
          },
        )
      },

      /** Directly set/replace structured requirements fields by hand - no
       * AI call (`app/api/routes/requirements.py`'s `edit_requirements`).
       * Unlike `refineRun`, works from any stage except the transient
       * `"generating"` one, including `"architecture"`/`"work_breakdown"` -
       * exists to unblock a diagram-originated session (empty functional/
       * non-functional requirements) that otherwise can never generate a
       * work breakdown. Every field on `body` is optional and independently
       * means "leave unchanged" when omitted; an explicit empty list clears
       * that field. */
      editRequirements: (sessionId: string, body: ManualRequirementsRequest) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/requirements`, {
          method: "PUT",
          body: JSON.stringify(body),
        }),

      acceptRun: (sessionId: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/accept`, {
          method: "POST",
        }),

      refineArchitecture: (sessionId: string, input: string) =>
        request<RequirementsRunView>(
          `/requirements-runs/${sessionId}/refine-architecture`,
          {
            method: "POST",
            body: JSON.stringify({ input }),
          },
        ),

      approveRun: (sessionId: string, reason?: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/approve`, {
          method: "POST",
          body: JSON.stringify({ reason: reason ?? null }),
        }),

      rejectRun: (sessionId: string, reason?: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/reject`, {
          method: "POST",
          body: JSON.stringify({ reason: reason ?? null }),
        }),

      // --- Artifact history (app/api/routes/artifacts.py) - read-only,
      // never generates anything; only exposes what's already persisted.

      listRequirementsVersions: (sessionId: string) =>
        request<number[]>(`/requirements-runs/${sessionId}/requirements/versions`),

      getRequirementsVersion: (sessionId: string, version: number) =>
        request<RequirementsArtifact>(
          `/requirements-runs/${sessionId}/requirements/${version}`,
        ),

      listArchitectureVersions: (sessionId: string) =>
        request<number[]>(`/requirements-runs/${sessionId}/architecture/versions`),

      getArchitectureVersion: (sessionId: string, version: number) =>
        request<SystemDesignArtifact>(
          `/requirements-runs/${sessionId}/architecture/${version}`,
        ),

      getArchitectureDiagram: (sessionId: string, version: number) =>
        requestText(`/requirements-runs/${sessionId}/architecture/${version}/diagram`),

      // --- Work breakdown (app/api/routes/work_breakdown.py) - the fourth
      // pipeline stage, generated/refined only once the architecture has
      // been approved (see `_require_architecture_approved` there).

      generateWorkBreakdown: (sessionId: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/work-breakdown`, {
          method: "POST",
        }),

      refineWorkBreakdown: (sessionId: string, input: string) =>
        request<RequirementsRunView>(
          `/requirements-runs/${sessionId}/work-breakdown/refine`,
          {
            method: "POST",
            body: JSON.stringify({ input }),
          },
        ),

      getWorkBreakdown: (sessionId: string) =>
        request<WorkBreakdownArtifact>(`/requirements-runs/${sessionId}/work-breakdown`),

      listWorkBreakdownVersions: (sessionId: string) =>
        request<number[]>(`/requirements-runs/${sessionId}/work-breakdown/versions`),

      getWorkBreakdownVersion: (sessionId: string, version: number) =>
        request<WorkBreakdownArtifact>(
          `/requirements-runs/${sessionId}/work-breakdown/${version}`,
        ),

      exportWorkBreakdownCsv: (sessionId: string) =>
        downloadFile(
          `/requirements-runs/${sessionId}/work-breakdown/export`,
          `work-breakdown-${sessionId}.csv`,
        ),
    }),
    [request, requestText, downloadFile],
  )
}
