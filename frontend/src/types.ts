// Mirrors app/models.py and app/design/models.py on the backend. Kept as
// plain interfaces (not generated from the FastAPI OpenAPI schema) since
// this first pass is hand-rolled - see README "Next steps" for turning
// this into a generated client later.

export interface Actor {
  name: string
  description: string
}

export interface Requirement {
  id: string
  description: string
  priority: string
  rationale: string | null
}

export interface Assumption {
  id: string
  assumption: string
  reason: string
  confidence: string
}

export interface OpenQuestion {
  id: string
  question: string
  reason: string
  blocking: boolean
}

// Mirrors app/api/routes/requirements.py's `ManualRequirementInput`/
// `ManualRequirementsRequest` - the body for `PUT
// /requirements-runs/{id}/requirements` (`editRequirements` in api.ts), a
// plain data-entry route (no AI call) that lets a caller directly set
// structured requirements fields. Deliberately has no `id` field on
// `ManualRequirementInput`: IDs (`FR-00N`/`NFR-00N`) are always assigned by
// the backend, never taken from the caller.
export interface ManualRequirementInput {
  description: string
  priority: string
  rationale: string | null
}

// Every field is optional and independently means "leave unchanged" when
// omitted; an explicit empty list means "clear this list" - see the
// backend model's docstring. There is deliberately no `actors`/
// `assumptions`/`open_questions` field, matching the backend.
export interface ManualRequirementsRequest {
  business_goal?: string
  summary?: string
  functional_requirements?: ManualRequirementInput[]
  non_functional_requirements?: ManualRequirementInput[]
  data_requirements?: string[]
  integration_requirements?: string[]
  constraints?: string[]
}

export interface RequirementsArtifact {
  summary: string
  business_goal: string
  actors: Actor[]
  functional_requirements: Requirement[]
  non_functional_requirements: Requirement[]
  data_requirements: string[]
  integration_requirements: string[]
  constraints: string[]
  assumptions: Assumption[]
  open_questions: OpenQuestion[]
}

export interface DesignComponent {
  id: string
  name: string
  responsibility: string
  /** Short group/category name (e.g. "Client & Identity") shared by every
   * component that belongs together - blank for older/unclassified
   * designs. Drives per-domain clustering in the rendered diagram; see
   * app/design/diagram.py. */
  domain: string
  /** Technology-agnostic trust/security boundary (e.g. "Public", "DMZ",
   * "Private", "Internal") - "TBD" when unknown. Never an Azure-specific
   * networking concept; see `AzureServiceMapping.connectivity`/
   * `.trust_zone` for that. */
  trust_zone: string
  requirement_ids: string[]
}

export interface DesignInterface {
  id: string
  name: string
  purpose: string
  /** May be a `DesignComponent.id` or an `Actor.id`. */
  source_component: string
  /** May be a `DesignComponent.id` or an `Actor.id`. */
  target_component: string
  /** "sync" (request/response) or "async" (event/message). */
  flow_type: string
  requirement_ids: string[]
}

export interface ExternalDependency {
  id: string
  name: string
  purpose: string
  used_by_components: string[]
}

/** An external human or system actor interacting with the architecture
 * from OUTSIDE its boundary - the mirror image of `ExternalDependency`
 * (which this architecture calls OUT to). */
export interface Actor {
  id: string
  name: string
  /** "user" | "external_system" */
  kind: string
  description: string
}

/** Maps one logical component/actor/external dependency (by id) to its
 * concrete Azure implementation - the traceability link between the
 * Logical Architecture Diagram and the Azure Service Mapping Diagram. */
export interface AzureServiceMapping {
  id: string
  component_id: string
  azure_service: string
  service_category: string
  rationale: string
  alternatives_considered: string[]
  /** "public-endpoint" | "private-endpoint" | "vnet-internal" |
   * "internal-only" | "TBD" */
  connectivity: string
  /** "Public" | "DMZ" | "Private VNet" | "Internal" | "TBD" */
  trust_zone: string
}

/** An Azure service supporting the architecture without mapping 1:1 to
 * any single component - identity, networking, secrets, monitoring,
 * CI/CD. */
export interface SupportingAzureService {
  id: string
  azure_service: string
  category: string
  purpose: string
  rationale: string
  applies_to_components: string[]
}

export interface DesignAssumption {
  id: string
  assumption: string
  reason: string
}

export interface DesignQuestion {
  id: string
  question: string
  reason: string
}

export interface SystemDesignArtifact {
  architecture_summary: string
  components: DesignComponent[]
  interfaces: DesignInterface[]
  external_dependencies: ExternalDependency[]
  actors: Actor[]
  azure_mappings: AzureServiceMapping[]
  supporting_azure_services: SupportingAzureService[]
  assumptions: DesignAssumption[]
  open_questions: DesignQuestion[]
}

export interface WorkBreakdownTask {
  task: string
  description: string
  effort: string
  requirement_ids: string[]
  architecture_ids: string[]
}

export interface WorkBreakdownStory {
  story: string
  tasks: WorkBreakdownTask[]
}

export interface WorkBreakdownFeature {
  feature: string
  stories: WorkBreakdownStory[]
}

export interface WorkBreakdownAmbiguity {
  kind: string
  description: string
  related_ids: string[]
}

export interface WorkBreakdownArtifact {
  features: WorkBreakdownFeature[]
  ambiguities: WorkBreakdownAmbiguity[]
}

export interface DesignTable {
  caption: string
  headers: string[]
  rows: string[][]
}

// One entry in a flat, ordered list of document sections - `level`
// (1-3) carries the section's own heading depth rather than nesting,
// matching the backend's `app.domain.technical_design.DesignSection`.
export interface DesignSection {
  title: string
  level: number
  body: string
  bullets: string[]
  numbered_steps: string[]
  table: DesignTable | null
  include_diagram: boolean
}

export interface TechnicalDesignArtifact {
  document_title: string
  system_name: string
  version: string
  executive_summary: string
  sections: DesignSection[]
}

// The rendered `.docx` export's metadata - `downloadTechnicalDesignExport`
// in api.ts fetches the actual file bytes as a Blob separately; this
// shape isn't currently surfaced in the UI but mirrors the backend's
// `TechnicalDesignExport` for completeness/future use.
export interface TechnicalDesignExport {
  docx_base64: string
  filename: string
  heading_count: number
  table_count: number
  diagram_embedded: boolean
  byte_count: number
  warnings: string[]
}

// "requirements" | "generating" | "architecture" - matches
// app/infrastructure/session_store.py's SessionRecord.stage exactly. Kept
// as `string` rather than a union so an unrecognized value from an older
// backend doesn't fail type-checking here; UI code should not assume it's
// exhaustive.
export type SessionStage = string

// "pending" | "approved" | "rejected" - matches SessionRecord.approval_status.
// Same "kept as string" reasoning as SessionStage above.
export type ApprovalStatus = string

export interface ApprovalDecision {
  decision: ApprovalStatus
  architecture_version: number
  reason: string | null
  decided_by: string | null
  decided_at: string
}

// Mirrors GET /me's response (app/web/main.py's `whoami`). `roles` is every
// Entra ID App Role assigned to the caller (see app/security/auth.py's
// `roles_of`) - with AUTH_ENABLED=false on the backend this is every role
// (ALL_APP_ROLES), not empty, since every `require_role` check passes
// regardless of role in that mode; see useCurrentUser.ts for how the UI
// uses this to grey out actions.
export interface MeResponse {
  authenticated: boolean
  principal: string
  oid: string
  roles: string[]
}

export interface RequirementsRunView {
  session_id: string
  /** User-editable display label, set via `POST .../rename` - `null` until
   * someone renames the session (see Sidebar.tsx, which falls back to a
   * shortened `session_id` while this is unset). */
  name: string | null
  /** Who started this session - only ever populated (and only ever shown
   * by the UI) when the caller is browsing sessions they don't own, i.e.
   * an Admin viewing `GET /requirements-runs`'s cross-user list; see
   * `app/api/routes/requirements.py`'s `RequirementsRunView`. */
  owner_name: string | null
  stage: SessionStage
  requirements_version: number
  requirements: RequirementsArtifact | null
  source_filename: string | null
  design_version: number
  design: SystemDesignArtifact | null
  design_blob: string | null
  /** Blob name of the persisted Logical Architecture Diagram SVG. */
  diagram_blob: string | null
  /** Blob name of the persisted Azure Service Mapping Diagram SVG -
   * `null` for any design version rendered before this second diagram
   * existed. */
  azure_diagram_blob: string | null
  approval_status: ApprovalStatus
  approval_history: ApprovalDecision[]
  work_breakdown_version: number
  work_breakdown: WorkBreakdownArtifact | null
  work_breakdown_blob: string | null
  technical_design_version: number
  technical_design: TechnicalDesignArtifact | null
  technical_design_blob: string | null
  technical_design_export_blob: string | null
  error: string | null
}
