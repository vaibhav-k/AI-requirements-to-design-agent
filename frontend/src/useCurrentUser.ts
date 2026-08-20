import { useEffect, useState } from "react"
import { useIsAuthenticated } from "@azure/msal-react"

import { useRequirementsApi } from "./api"

export interface CurrentUser {
  /** Entra ID App Roles the backend's `/me` reports for this caller - see
   * `MeResponse` in types.ts. Empty until `loaded` is true. */
  roles: string[]
  /** False until the first `/me` call settles (success or failure). Callers
   * should treat "not yet loaded" as "don't grey anything out yet" rather
   * than "no roles" - see Workspace.tsx's permission booleans, which all
   * default to `true` while `!loaded`. */
  loaded: boolean
}

/** The signed-in caller's effective Entra ID App Roles, fetched from
 * `GET /me` - mirrors the backend's `require_role` checks so the UI can
 * grey out actions before a round trip, not as its own source of truth
 * (see permissions.ts's header comment: the backend is still what
 * actually enforces this).
 *
 * Works in every auth mode, including anonymous (`AUTH_ENABLED=false`) -
 * `/me` reports every role in that mode (see `app/web/main.py`'s
 * `whoami`), so nothing is greyed out locally without auth configured,
 * matching the backend's own "no-op when auth is disabled" behavior.
 */
export function useCurrentUser(): CurrentUser {
  const isAuthenticated = useIsAuthenticated()
  const api = useRequirementsApi()
  const [roles, setRoles] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false

    api
      .getMe()
      .then((me) => {
        if (cancelled) return
        setRoles(me.roles)
        setLoaded(true)
      })
      .catch(() => {
        // A failed /me call (backend unreachable, transient network issue)
        // is treated as "roles unknown," not "no roles" - see `loaded`'s
        // doc comment. The action's own request still enforces the real
        // permission either way, so this can't open up anything the
        // backend wouldn't otherwise allow.
        if (!cancelled) setLoaded(true)
      })

    return () => {
      cancelled = true
    }
    // Re-fetch whenever sign-in state changes (sign in, sign out, switch
    // account) - `api` is memoized (see useRequirementsApi) so its
    // identity alone doesn't cause extra re-fetches.
  }, [api, isAuthenticated])

  return { roles, loaded }
}
