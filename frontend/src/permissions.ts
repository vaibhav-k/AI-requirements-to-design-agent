// Mirrors app/security/auth.py's role constants and `require_role`'s
// "Admin always passes" rule exactly - kept in sync by hand, same as
// Conversation.tsx's SUPPORTED_UPLOAD_EXTENSIONS mirroring app/ingestion.py.
// This is a UI convenience only: it decides what to grey out, never what
// the backend actually allows - the real enforcement is server-side
// `require_role`, and every action here still goes through that same
// check on the actual request. If these two ever disagree (a role was
// just revoked and the frontend's cached roles are stale), the backend
// wins and the request fails with a 403 that api.ts's error handling
// surfaces - see friendlyErrorMessage in Workspace.tsx.

export const ROLE_ADMIN = "Admin"
export const ROLE_ARCHITECT = "Architect"
export const ROLE_REVIEWER = "Reviewer"
export const ROLE_USER = "User"

/** Whether `roles` includes `Admin` or any role in `allowed` - `Admin`
 * always passes, regardless of `allowed`, matching `require_role`. */
export function hasAnyRole(roles: string[], allowed: string[]): boolean {
  return roles.includes(ROLE_ADMIN) || allowed.some((role) => roles.includes(role))
}
