import { useCallback, useMemo } from "react"
import { InteractionRequiredAuthError, type IPublicClientApplication } from "@azure/msal-browser"
import { useMsal } from "@azure/msal-react"

import { apiBaseUrl, authIsConfigured, loginRequest } from "./authConfig"
import type { RequirementsArtifact, RequirementsRunView, SystemDesignArtifact } from "./types"

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
    // Response body wasn't JSON (or was empty) — fall through to the
    // generic message below rather than let this throw mask the real error.
  }
  return `Request failed with status ${response.status}`
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
      const result = await instance.acquireTokenPopup(request)
      return result.accessToken
    }
    throw error
  }
}

/** Typed client for the `/requirements-runs` endpoints (app/api/routes/requirements.py).
 *
 * A hook, not a plain module, because acquiring a token needs the active
 * MSAL account — `useMsal()` is the only supported way to reach that
 * outside a class component.
 */
export function useRequirementsApi() {
  const { instance, accounts } = useMsal()

  const fetchWithAuth = useCallback(
    async (path: string, init: RequestInit = {}): Promise<Response> => {
      const token = await acquireToken(instance, accounts[0])
      const headers = new Headers(init.headers)
      if (init.body) {
        headers.set("Content-Type", "application/json")
      }
      if (token) {
        headers.set("Authorization", `Bearer ${token}`)
      }
      return fetch(`${apiBaseUrl}${path}`, { ...init, headers })
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

  /** Like `request`, but for endpoints returning a body that isn't JSON —
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

  // Memoized so the returned object (and each method on it) is stable
  // across renders as long as `request`/`requestText` are (which are
  // themselves stable unless the active MSAL account changes) — lets
  // callers safely list e.g. `api.listRuns` in a `useEffect` dependency
  // array instead of needing to suppress the exhaustive-deps warning.
  return useMemo(
    () => ({
      listRuns: () => request<RequirementsRunView[]>("/requirements-runs"),

      startRun: (input: string) =>
        request<RequirementsRunView>("/requirements-runs", {
          method: "POST",
          body: JSON.stringify({ input }),
        }),

      getRun: (sessionId: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}`),

      refineRun: (sessionId: string, input: string) =>
        request<RequirementsRunView>(`/requirements-runs/${sessionId}/refine`, {
          method: "POST",
          body: JSON.stringify({ input }),
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

      // --- Artifact history (app/api/routes/artifacts.py) — read-only,
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
    }),
    [request, requestText],
  )
}
