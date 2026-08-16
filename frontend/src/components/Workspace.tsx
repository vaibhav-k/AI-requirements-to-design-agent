import { useEffect, useState } from "react"

import { ApiError, useRequirementsApi } from "../api"
import type { RequirementsArtifact, RequirementsRunView, SystemDesignArtifact } from "../types"
import { ArtifactPanel, type ArtifactTab } from "./ArtifactPanel"
import { Conversation, type ConversationStatus, type TranscriptEntry } from "./Conversation"

interface WorkspaceProps {
  /** null means "no session yet" — the conversation is offered as the way
   * to start one, mirroring the old NewRunForm but without a separate view. */
  sessionId: string | null
  onSessionCreated: (sessionId: string) => void
}

function summarizeRequirements(requirements: RequirementsArtifact): string {
  return `${requirements.summary}\n\nBusiness goal: ${requirements.business_goal}`
}

function summarizeDesign(design: SystemDesignArtifact): string {
  return design.architecture_summary
}

/** Distinguishes the two ways `POST /accept` can fail (see
 * app/design/workflow.py's DesignGenerationWorkflowError): the analyzer's
 * own architecture validation rejected the design it produced, vs. the
 * generation call itself failed (model error, malformed JSON, etc.).
 * This is read off the real error text, not a fabricated progress signal —
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
        // Jump straight to Architecture when opening a session that
        // already has one — Requirements only makes sense as the default
        // for a session that hasn't been accepted yet.
        setActiveTab(result.design ? "architecture" : "requirements")
        if (result.requirements) {
          appendEntry({ role: "assistant", content: summarizeRequirements(result.requirements) })
        }
        if (result.design) {
          appendEntry({ role: "assistant", content: summarizeDesign(result.design) })
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
          content: err instanceof ApiError ? err.message : "Could not load this session.",
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
            content: err instanceof ApiError ? err.message : "Could not start the session.",
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
            err instanceof ApiError ? err.message : "Could not refine the architecture."
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

    if (run && run.stage !== "requirements") {
      // Covers the "generating" stage — a refine/accept for this session is
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
          content: err instanceof ApiError ? err.message : "Could not refine requirements.",
          tone: "error",
        })
      })
      .finally(() => setBusy(false))
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
          err instanceof ApiError ? err.message : "Could not generate the architecture."
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

  const statusLabel: Record<ConversationStatus, string> = {
    idle: "Ready",
    loading: "Loading",
    processing: "Processing",
    ready: "Ready",
    error: "Error",
  }

  const canSend = !busy && status !== "loading"
  const canAccept = Boolean(run && run.stage === "requirements" && run.requirements)
  const hasRequirements = Boolean(run?.requirements)
  const hasArchitecture = Boolean(run?.design)

  return (
    <div className="workspace">
      <div className="workspace-conversation">
        <Conversation
          transcript={transcript}
          status={status}
          statusLabel={statusLabel[status]}
          onSend={handleSend}
          onAccept={handleAccept}
          canAccept={canAccept}
          acceptLabel={busy ? "Generating architecture…" : "Accept & generate architecture"}
          canSend={canSend}
          placeholder={
            sessionId
              ? "Ask for a change…"
              : "Describe what you want to build, e.g. a todo app for small teams with due dates and shared boards."
          }
        />
      </div>

      <div className="workspace-artifacts">
        {sessionId ? (
          <ArtifactPanel
            sessionId={sessionId}
            refreshKey={refreshKey}
            hasRequirements={hasRequirements}
            hasArchitecture={hasArchitecture}
            activeTab={activeTab}
            onTabChange={setActiveTab}
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
