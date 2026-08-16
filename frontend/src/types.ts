// Mirrors app/models.py and app/design/models.py on the backend. Kept as
// plain interfaces (not generated from the FastAPI OpenAPI schema) since
// this first pass is hand-rolled — see README "Next steps" for turning
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
  requirement_ids: string[]
}

export interface DesignInterface {
  id: string
  name: string
  purpose: string
  source_component: string
  target_component: string
  requirement_ids: string[]
}

export interface ExternalDependency {
  id: string
  name: string
  purpose: string
  used_by_components: string[]
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
  assumptions: DesignAssumption[]
  open_questions: DesignQuestion[]
}

// "requirements" | "generating" | "architecture" — matches
// app/infrastructure/session_store.py's SessionRecord.stage exactly. Kept
// as `string` rather than a union so an unrecognized value from an older
// backend doesn't fail type-checking here; UI code should not assume it's
// exhaustive.
export type SessionStage = string

export interface RequirementsRunView {
  session_id: string
  stage: SessionStage
  requirements_version: number
  requirements: RequirementsArtifact | null
  design_version: number
  design: SystemDesignArtifact | null
  design_blob: string | null
  diagram_blob: string | null
  error: string | null
}
