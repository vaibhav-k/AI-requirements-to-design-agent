import { useEffect, useState } from "react"

import { friendlyErrorMessage, useRequirementsApi } from "../api"
import { hasAnyRole, ROLE_ARCHITECT, ROLE_REVIEWER, ROLE_USER } from "../permissions"
import type {
  RequirementsArtifact,
  RequirementsRunView,
  SystemDesignArtifact,
  TechnicalDesignArtifact,
  WorkBreakdownArtifact,
} from "../types"
import { useCurrentUser } from "../useCurrentUser"
import { useResizableWidth } from "../useResizableWidth"
import { ArtifactPanel, type ArtifactTab } from "./ArtifactPanel"
import { Conversation, type ConversationStatus, type TranscriptEntry } from "./Conversation"
import { DIAGRAM_STUB_BUSINESS_GOAL } from "./RequirementsEditor"

interface WorkspaceProps {
  /** null means "no session yet" - the conversation is offered as the way
   * to start one, mirroring the old NewRunForm but without a separate view. */
  sessionId: string | null
  onSessionCreated: (sessionId: string) => void
}

function summarizeRequirements(requirements: RequirementsArtifact): string {
  const base = `${requirements.summary}\n\nBusiness goal: ${requirements.business_goal}`
  // A diagram-uploaded session gets this exact placeholder rather than a
  // real business goal (see `_stub_requirements_from_diagram`) - call out
  // where to fix that instead of leaving the raw placeholder unexplained.
  if (requirements.business_goal === DIAGRAM_STUB_BUSINESS_GOAL) {
    return (
      `${base}\n\nThis session started from a diagram upload, so the ` +
      "business goal, summary, and functional/non-functional requirements " +
      "weren't specified. Head to the Requirements tab to fill them in " +
      "there - Task Planning needs at least one functional or " +
      "non-functional requirement before it can generate a work breakdown."
    )
  }
  return base
}

function summarizeDesign(design: SystemDesignArtifact): string {
  return design.architecture_summary
}

/** A one-line summary of a just-generated/refined breakdown for the
 * transcript - counts only, never invents content, same spirit as
 * `summarizeRequirements`/`summarizeDesign` above. */
function summarizeWorkBreakdown(breakdown: WorkBreakdownArtifact): string {
  const featureCount = breakdown.features.length
  const storyCount = breakdown.features.reduce((sum, f) => sum + f.stories.length, 0)
  const taskCount = breakdown.features.reduce(
    (sum, f) => sum + f.stories.reduce((s, story) => s + story.tasks.length, 0),
    0,
  )
  return (
    `Work breakdown: ${featureCount} feature${featureCount === 1 ? "" : "s"}, ` +
    `${storyCount} stor${storyCount === 1 ? "y" : "ies"}, ` +
    `${taskCount} task${taskCount === 1 ? "" : "s"}.`
  )
}

/** A one-line summary of a just-generated/refined technical design
 * document for the transcript - same "counts only, never invents
 * content" spirit as `summarizeWorkBreakdown`. */
function summarizeTechnicalDesign(document: TechnicalDesignArtifact): string {
  const sectionCount = document.sections.length
  return (
    `Technical design document "${document.document_title}": ` +
    `${sectionCount} section${sectionCount === 1 ? "" : "s"}.`
  )
}

/** Distinguishes the two ways `POST /accept` can fail (see
 * app/design/workflow.py's DesignGenerationWorkflowError): the analyzer's
 * own architecture validation rejected the design it produced, vs. the
 * generation call itself failed (model error, malformed JSON, etc.).
 * This is read off the real error text, not a fabricated progress signal -
 * the backend call is a single synchronous request either way. */
function isValidationFailure(message: string): boolean {
  return message.startsWith("Architecture validation failed:")
}

function nextEntryId(): string {
  return crypto.randomUUID()
}

export function Workspace({ sessionId, onSessionCreated }: WorkspaceProps) {
  const api = useRequirementsApi()
  const [run, setRun] = useState<RequirementsRunView | null>(null)
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([])
  const [status, setStatus] = useState<ConversationStatus>(sessionId ? "loading" : "idle")
  const [busy, setBusy] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [activeTab, setActiveTab] = useState<ArtifactTab>("requirements")

  const appendEntry = (entry: Omit<TranscriptEntry, "id">) => {
    setTranscript((current) => [...current, { ...entry, id: nextEntryId() }])
  }

  // Load (or reset) the session whenever the active session id changes.
  useEffect(() => {
    if (!sessionId) {
      setRun(null)
      setTranscript([])
      setStatus("idle")
      setActiveTab("requirements")
      return
    }
    let cancelled = false
    setStatus("loading")
    setRun(null)
    setTranscript([])
    api
      .getRun(sessionId)
      .then((result) => {
        if (cancelled) return
        setRun(result)
        setStatus(result.error ? "error" : "ready")
        // Jump straight to the furthest stage reached when opening a
        // session that already has one - Requirements/Architecture only
        // make sense as the default for a session that hasn't moved past
        // them yet.
        setActiveTab(
          result.technical_design
            ? "technical_design"
            : result.work_breakdown
              ? "work_breakdown"
              : result.design
                ? "architecture"
                : "requirements",
        )
        if (result.requirements) {
          appendEntry({ role: "assistant", content: summarizeRequirements(result.requirements) })
        }
        if (result.design) {
          appendEntry({ role: "assistant", content: summarizeDesign(result.design) })
        }
        if (result.work_breakdown) {
          appendEntry({ role: "assistant", content: summarizeWorkBreakdown(result.work_breakdown) })
        }
        if (result.technical_design) {
          appendEntry({
            role: "assistant",
            content: summarizeTechnicalDesign(result.technical_design),
          })
        }
        if (result.error) {
          appendEntry({ role: "assistant", content: result.error, tone: "error" })
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setStatus("error")
        appendEntry({
          role: "assistant",
          content: friendlyErrorMessage(err, "Could not load this session."),
          tone: "error",
        })
      })
    return () => {
      cancelled = true
    }
    // `api` is memoized (see useRequirementsApi) so its identity is stable
    // across renders unless the underlying MSAL account changes.
  }, [sessionId, api])

  const handleSend = (input: string) => {
    appendEntry({ role: "user", content: input })

    if (!sessionId) {
      setBusy(true)
      setStatus("processing")
      api
        .startRun(input)
        .then((result) => {
          setRun(result)
          setStatus("ready")
          if (result.requirements) {
            appendEntry({ role: "assistant", content: summarizeRequirements(result.requirements) })
          }
          onSessionCreated(result.session_id)
        })
        .catch((err: unknown) => {
          setStatus("error")
          appendEntry({
            role: "assistant",
            content: friendlyErrorMessage(err, "Could not start the session."),
            tone: "error",
          })
        })
        .finally(() => setBusy(false))
      return
    }

    if (run && run.stage === "architecture") {
      setBusy(true)
      setStatus("processing")
      api
        .refineArchitecture(sessionId, input)
        .then((result) => {
          setRun(result)
          setStatus(result.error ? "error" : "ready")
          setRefreshKey((key) => key + 1)
          if (result.design) {
            appendEntry({ role: "assistant", content: summarizeDesign(result.design) })
          }
          if (result.error) {
            appendEntry({ role: "assistant", content: result.error, tone: "error" })
          }
        })
        .catch((err: unknown) => {
          setStatus("error")
          const message =
            friendlyErrorMessage(err, "Could not refine the architecture.")
          appendEntry({
            role: "assistant",
            content: isValidationFailure(message)
              ? message
              : `Architecture refinement failed: ${message}`,
            tone: "error",
          })
        })
        .finally(() => setBusy(false))
      return
    }

    if (run && run.stage === "work_breakdown") {
      setBusy(true)
      setStatus("processing")
      api
        .refineWorkBreakdown(sessionId, input)
        .then((result) => {
          setRun(result)
          setStatus(result.error ? "error" : "ready")
          setRefreshKey((key) => key + 1)
          if (result.work_breakdown) {
            appendEntry({ role: "assistant", content: summarizeWorkBreakdown(result.work_breakdown) })
          }
          if (result.error) {
            appendEntry({ role: "assistant", content: result.error, tone: "error" })
          }
        })
        .catch((err: unknown) => {
          setStatus("error")
          appendEntry({
            role: "assistant",
            content: `Work breakdown refinement failed: ${friendlyErrorMessage(
              err,
              "Could not refine the work breakdown.",
            )}`,
            tone: "error",
          })
        })
        .finally(() => setBusy(false))
      return
    }

    if (run && run.stage === "technical_design") {
      setBusy(true)
      setStatus("processing")
      api
        .refineTechnicalDesign(sessionId, input)
        .then((result) => {
          setRun(result)
          setStatus(result.error ? "error" : "ready")
          setRefreshKey((key) => key + 1)
          if (result.technical_design) {
            appendEntry({
              role: "assistant",
              content: summarizeTechnicalDesign(result.technical_design),
            })
          }
          if (result.error) {
            appendEntry({ role: "assistant", content: result.error, tone: "error" })
          }
        })
        .catch((err: unknown) => {
          setStatus("error")
          appendEntry({
            role: "assistant",
            content: `Technical design refinement failed: ${friendlyErrorMessage(
              err,
              "Could not refine the technical design document.",
            )}`,
            tone: "error",
          })
        })
        .finally(() => setBusy(false))
      return
    }

    if (run && run.stage !== "requirements") {
      // Covers the "generating" stage - a refine/accept for this session is
      // already in flight (this one, or a concurrent request), matching the
      // backend's own double-submit guard (app/api/routes/requirements.py).
      appendEntry({
        role: "assistant",
        content:
          "This session's architecture is currently being generated. Please wait for it to finish.",
      })
      return
    }

    setBusy(true)
    setStatus("processing")
    api
      .refineRun(sessionId, input)
      .then((result) => {
        setRun(result)
        setStatus(result.error ? "error" : "ready")
        setRefreshKey((key) => key + 1)
        if (result.requirements) {
          appendEntry({ role: "assistant", content: summarizeRequirements(result.requirements) })
        }
        if (result.error) {
          appendEntry({ role: "assistant", content: result.error, tone: "error" })
        }
      })
      .catch((err: unknown) => {
        setStatus("error")
        appendEntry({
          role: "assistant",
          content: friendlyErrorMessage(err, "Could not refine requirements."),
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
  }

  const handleSendFile = (file: File, notes?: string) => {
    appendEntry({
      role: "user",
      content: notes ? `Scanned file: ${file.name}\n\n${notes}` : `Scanned file: ${file.name}`,
    })

    if (!sessionId) {
      setBusy(true)
      setStatus("processing")
      api
        .startRunFromUpload(file, notes)
        .then((result) => {
          setRun(result)
          setStatus("ready")
          if (result.requirements) {
            appendEntry({ role: "assistant", content: summarizeRequirements(result.requirements) })
          }
          onSessionCreated(result.session_id)
        })
        .catch((err: unknown) => {
          setStatus("error")
          appendEntry({
            role: "assistant",
            content: friendlyErrorMessage(err, "Could not scan the file."),
            tone: "error",
          })
        })
        .finally(() => setBusy(false))
      return
    }

    if (run && run.stage !== "requirements") {
      // Same guard as handleSend: file upload only makes sense while the
      // session is still refining requirements, matching the backend's
      // /refine/upload route (409 outside STAGE_REQUIREMENTS).
      appendEntry({
        role: "assistant",
        content:
          "This session has already moved past the requirements stage; scanning a new file isn't possible here.",
      })
      return
    }

    setBusy(true)
    setStatus("processing")
    api
      .refineRunFromUpload(sessionId, file, notes)
      .then((result) => {
        setRun(result)
        setStatus(result.error ? "error" : "ready")
        setRefreshKey((key) => key + 1)
        if (result.requirements) {
          appendEntry({ role: "assistant", content: summarizeRequirements(result.requirements) })
        }
        if (result.error) {
          appendEntry({ role: "assistant", content: result.error, tone: "error" })
        }
      })
      .catch((err: unknown) => {
        setStatus("error")
        appendEntry({
          role: "assistant",
          content: friendlyErrorMessage(err, "Could not scan the file."),
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
  }

  /** Applies a `PUT .../requirements` (manual, non-AI edit) result back into
   * this session's state - same "adopt the returned view, bump refreshKey"
   * shape every other mutation here follows. Unlike those, the API call
   * itself lives in RequirementsEditor (closer to its own form state and
   * error banner, the same "panel owns its own simple mutation" pattern
   * ArtifactPanel's CSV export already uses), so this is only ever called
   * with an already-successful result. */
  const handleRequirementsSaved = (result: RequirementsRunView) => {
    setRun(result)
    setRefreshKey((key) => key + 1)
    appendEntry({
      role: "assistant",
      content: result.requirements
        ? summarizeRequirements(result.requirements)
        : "Requirements updated.",
    })
  }

  const handleAccept = () => {
    if (!sessionId) return
    setBusy(true)
    setStatus("processing")
    appendEntry({ role: "user", content: "Accept & generate architecture" })
    api
      .acceptRun(sessionId)
      .then((result) => {
        setRun(result)
        setRefreshKey((key) => key + 1)
        if (result.design) {
          setStatus("ready")
          setActiveTab("architecture")
          appendEntry({ role: "assistant", content: summarizeDesign(result.design) })
        } else if (result.error) {
          setStatus("error")
          appendEntry({ role: "assistant", content: result.error, tone: "error" })
        } else {
          setStatus("ready")
        }
      })
      .catch((err: unknown) => {
        setStatus("error")
        const message =
          friendlyErrorMessage(err, "Could not generate the architecture.")
        appendEntry({
          role: "assistant",
          content: isValidationFailure(message)
            ? message
            : `Architecture generation failed: ${message}`,
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
  }

  const handleApprove = () => {
    if (!sessionId) return
    setBusy(true)
    setStatus("processing")
    appendEntry({ role: "user", content: "Approve architecture" })
    api
      .approveRun(sessionId)
      .then((result) => {
        setRun(result)
        setStatus("ready")
        appendEntry({
          role: "assistant",
          content: `Architecture v${result.design_version} approved.`,
        })
      })
      .catch((err: unknown) => {
        setStatus("error")
        appendEntry({
          role: "assistant",
          content: friendlyErrorMessage(err, "Could not record the approval."),
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
  }

  const handleReject = () => {
    if (!sessionId) return
    setBusy(true)
    setStatus("processing")
    appendEntry({ role: "user", content: "Reject architecture" })
    api
      .rejectRun(sessionId)
      .then((result) => {
        setRun(result)
        setStatus("ready")
        appendEntry({
          role: "assistant",
          content: `Architecture v${result.design_version} rejected. Describe what should change and it'll be refined.`,
        })
      })
      .catch((err: unknown) => {
        setStatus("error")
        appendEntry({
          role: "assistant",
          content: friendlyErrorMessage(err, "Could not record the rejection."),
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
  }

  const handleGenerateBreakdown = () => {
    if (!sessionId) return
    setBusy(true)
    setStatus("processing")
    appendEntry({ role: "user", content: "Generate work breakdown" })
    api
      .generateWorkBreakdown(sessionId)
      .then((result) => {
        setRun(result)
        setRefreshKey((key) => key + 1)
        if (result.work_breakdown) {
          setStatus("ready")
          setActiveTab("work_breakdown")
          appendEntry({ role: "assistant", content: summarizeWorkBreakdown(result.work_breakdown) })
        } else if (result.error) {
          setStatus("error")
          appendEntry({ role: "assistant", content: result.error, tone: "error" })
        } else {
          setStatus("ready")
        }
      })
      .catch((err: unknown) => {
        setStatus("error")
        const detail = friendlyErrorMessage(err, "Could not generate the work breakdown.")
        // This specific validation failure (`GenerateWorkBreakdownUseCase
        // .execute`'s own guard, surfaced verbatim as the backend's 422
        // detail) has one fix: add a requirement in the Requirements tab -
        // most often hit by a diagram-originated session, whose
        // requirements start out empty by design (see
        // `_stub_requirements_from_diagram`). Naming the fix here saves a
        // trip to figure out what "requirements must include at least one
        // functional or non-functional requirement" actually means to do
        // about it.
        const needsRequirements = detail.includes(
          "requirements must include at least one functional or non-functional requirement",
        )
        appendEntry({
          role: "assistant",
          content: needsRequirements
            ? `Work breakdown generation failed: ${detail} Head to the Requirements ` +
              "tab and add at least one functional or non-functional requirement, " +
              "then try again."
            : `Work breakdown generation failed: ${detail}`,
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
  }

  const handleGenerateTechnicalDesign = () => {
    if (!sessionId) return
    setBusy(true)
    setStatus("processing")
    appendEntry({ role: "user", content: "Generate technical design" })
    api
      .generateTechnicalDesign(sessionId)
      .then((result) => {
        setRun(result)
        setRefreshKey((key) => key + 1)
        if (result.technical_design) {
          setStatus("ready")
          setActiveTab("technical_design")
          appendEntry({
            role: "assistant",
            content: summarizeTechnicalDesign(result.technical_design),
          })
        } else if (result.error) {
          setStatus("error")
          appendEntry({ role: "assistant", content: result.error, tone: "error" })
        } else {
          setStatus("ready")
        }
      })
      .catch((err: unknown) => {
        setStatus("error")
        const detail = friendlyErrorMessage(
          err,
          "Could not generate the technical design document.",
        )
        appendEntry({
          role: "assistant",
          content: `Technical design generation failed: ${detail}`,
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
  }

  const statusLabel: Record<ConversationStatus, string> = {
    idle: "Ready",
    loading: "Loading",
    processing: "Processing",
    ready: "Ready",
    error: "Error",
  }

  const canSend = !busy && status !== "loading"
  const canAccept = Boolean(run && run.stage === "requirements" && run.requirements)
  const canUploadFile = !run || run.stage === "requirements"
  const canApprove = Boolean(run && run.stage === "architecture")
  const hasRequirements = Boolean(run?.requirements)
  const hasArchitecture = Boolean(run?.design)
  const architectureApproved = Boolean(run?.approval_status === "approved")
  const hasWorkBreakdown = Boolean(run?.work_breakdown)
  const canGenerateBreakdown = Boolean(
    run &&
      run.stage === "architecture" &&
      run.approval_status === "approved" &&
      run.work_breakdown_version === 0,
  )
  const hasTechnicalDesign = Boolean(run?.technical_design)
  const canGenerateTechnicalDesign = Boolean(
    run && run.stage === "work_breakdown" && run.technical_design_version === 0,
  )

  // Role gates - see permissions.ts and useCurrentUser.ts. Every check
  // defaults to "allowed" while `!loaded` (roles haven't been fetched
  // yet) so buttons don't flash disabled on first render; the backend
  // still enforces the real permission regardless of what's shown here.
  const { roles, loaded: rolesLoaded } = useCurrentUser()
  const canCreateRequirements = !rolesLoaded || hasAnyRole(roles, [ROLE_USER])
  const canManageArchitecture = !rolesLoaded || hasAnyRole(roles, [ROLE_ARCHITECT])
  const canDecideArchitecture = !rolesLoaded || hasAnyRole(roles, [ROLE_REVIEWER])
  // "Send" does quadruple duty (refine requirements, refine an already-
  // accepted architecture once `stage === "architecture"`, refine a work
  // breakdown once `stage === "work_breakdown"`, or refine a technical
  // design document once `stage === "technical_design"` - see
  // `handleSend`'s own branching above) - which role it needs depends on
  // which of those it would currently do. Refining a work breakdown or a
  // technical design document both need the same `Architect` role as
  // refining the architecture they trace back to (see
  // app/api/routes/work_breakdown.py's `refine_work_breakdown` and
  // app/api/routes/technical_design.py's `refine_technical_design`).
  const sendAllowed =
    run &&
    (run.stage === "architecture" ||
      run.stage === "work_breakdown" ||
      run.stage === "technical_design")
      ? canManageArchitecture
      : canCreateRequirements

  // Draggable split between the conversation and the artifact panel - see
  // useResizableWidth's docstring; persisted separately from the sidebar's
  // own width under its own localStorage key.
  const { width: conversationWidth, startDrag: startConversationDrag } = useResizableWidth({
    defaultWidth: 380,
    min: 280,
    max: 720,
    storageKey: "workspace-conversation-width",
  })

  return (
    <div className="workspace">
      <div className="workspace-conversation" style={{ flexBasis: conversationWidth }}>
        <Conversation
          transcript={transcript}
          status={status}
          statusLabel={statusLabel[status]}
          onSend={handleSend}
          sendAllowed={sendAllowed}
          sendDisabledReason={
            run &&
            (run.stage === "architecture" ||
              run.stage === "work_breakdown" ||
              run.stage === "technical_design")
              ? "Requires the Architect role."
              : "Requires the User role."
          }
          onSendFile={handleSendFile}
          canUploadFile={canUploadFile}
          hasRequirements={hasRequirements}
          uploadAllowed={canCreateRequirements}
          uploadDisabledReason="Requires the User role."
          sourceFilename={run?.source_filename}
          onAccept={handleAccept}
          canAccept={canAccept}
          acceptLabel={busy ? "Generating architecture…" : "Accept & generate architecture"}
          acceptAllowed={canManageArchitecture}
          acceptDisabledReason="Requires the Architect role."
          onApprove={handleApprove}
          onReject={handleReject}
          canApprove={canApprove}
          decisionAllowed={canDecideArchitecture}
          decisionDisabledReason="Requires the Reviewer role."
          onGenerateBreakdown={handleGenerateBreakdown}
          canGenerateBreakdown={canGenerateBreakdown}
          generateBreakdownLabel={busy ? "Generating work breakdown…" : "Generate work breakdown"}
          generateBreakdownAllowed={canManageArchitecture}
          generateBreakdownDisabledReason="Requires the Architect role."
          onGenerateTechnicalDesign={handleGenerateTechnicalDesign}
          canGenerateTechnicalDesign={canGenerateTechnicalDesign}
          generateTechnicalDesignLabel={
            busy ? "Generating technical design…" : "Generate technical design"
          }
          generateTechnicalDesignAllowed={canManageArchitecture}
          generateTechnicalDesignDisabledReason="Requires the Architect role."
          approvalStatus={run?.approval_status ?? "pending"}
          canSend={canSend}
          placeholder={
            sessionId
              ? "Ask for a change…"
              : "Describe what you want to build, e.g. a todo app for small teams with due dates and shared boards."
          }
        />
      </div>

      <div
        className="resize-handle"
        onMouseDown={startConversationDrag}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize conversation panel"
      />

      <div className="workspace-artifacts">
        {sessionId ? (
          <ArtifactPanel
            sessionId={sessionId}
            refreshKey={refreshKey}
            hasRequirements={hasRequirements}
            hasArchitecture={hasArchitecture}
            architectureApproved={architectureApproved}
            hasWorkBreakdown={hasWorkBreakdown}
            hasTechnicalDesign={hasTechnicalDesign}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            currentRequirements={run?.requirements ?? null}
            onRequirementsSaved={handleRequirementsSaved}
            editRequirementsAllowed={canCreateRequirements}
            editRequirementsDisabledReason="Requires the User role."
          />
        ) : (
          <p className="muted">
            Requirements and architecture will appear here once you start a session.
          </p>
        )}
      </div>
    </div>
  )
}
