import { useRef, useState } from "react"

// Mirrors app/ingestion.py's SUPPORTED_EXTENSIONS - kept in sync by hand
// (see that module's docstring for why these formats specifically).
const SUPPORTED_UPLOAD_EXTENSIONS = [
  ".txt",
  ".pdf",
  ".docx",
  ".png",
  ".jpg",
  ".jpeg",
]

export interface TranscriptEntry {
  id: string
  role: "user" | "assistant"
  content: string
  tone?: "error"
}

export type ConversationStatus = "idle" | "loading" | "processing" | "ready" | "error"

interface ConversationProps {
  readonly transcript: TranscriptEntry[]
  readonly status: ConversationStatus
  readonly statusLabel: string
  readonly onSend: (input: string) => void
  /** Whether the signed-in caller's App Role permits whatever "Send" would
   * currently do (create/refine requirements, or refine an architecture
   * once `stage === "architecture"` - see Workspace.tsx's `sendPermission`).
   * `false` greys the button out rather than hiding it - unlike
   * `canUploadFile`/`canAccept`/`canApprove` below, which govern whether
   * the action is *applicable* at this stage, this governs whether *this
   * caller* is allowed to do it; see permissions.ts. */
  readonly sendAllowed: boolean
  /** Tooltip shown on the disabled Send button when `!sendAllowed` - e.g.
   * "Requires the Architect role." */
  readonly sendDisabledReason?: string
  /** Upload a document (PDF/DOCX/PNG/JPG/JPEG/TXT) to be analyzed for
   * requirements instead of typing them - see `app/ingestion.py`. Any text
   * currently in the textarea is passed through as `notes`, appended to the
   * extracted document text (see `start_run_from_upload`/
   * `refine_run_from_upload` in app/api/routes/requirements.py). Only
   * offered while `canUploadFile` is true. Called from `handleSubmit`, not
   * from the file input's own `onChange` - attaching a file only stages it
   * (see `attachedFile` below); the user still has to press Send. */
  readonly onSendFile: (file: File, notes?: string) => void
  /** Whether the file-attach control should be shown at all - true only
   * while the session is still in the requirements stage (or hasn't
   * started yet) *and* no file has been attached yet this session
   * (`hasSubmittedFile` in Workspace.tsx) - attaching a file is a one-time
   * action, not a repeatable one. */
  readonly canUploadFile: boolean
  /** Whether requirements already exist for this session - purely a
   * tooltip/copy decision, not a permissions gate: it's what tells this
   * component whether attaching a file would call `start_run_from_upload`
   * (no requirements yet) or `refine_run_from_upload` (there are some
   * already, and the file's content is merged into them - see that
   * route's docstring). */
  readonly hasRequirements: boolean
  /** Same "grey out, don't hide" role gate as `sendAllowed`, for the
   * `User` role the `/upload` routes require. */
  readonly uploadAllowed: boolean
  readonly uploadDisabledReason?: string
  readonly onAccept: () => void
  /** Whether "Accept & generate architecture" should be offered at all -
   * only true once there are requirements to accept and the session hasn't
   * already moved past the requirements stage. */
  readonly canAccept: boolean
  readonly acceptLabel: string
  /** Same "grey out, don't hide" role gate as `sendAllowed`, for the
   * `Architect` role `POST .../accept` requires. */
  readonly acceptAllowed: boolean
  readonly acceptDisabledReason?: string
  readonly onApprove: () => void
  readonly onReject: () => void
  /** Whether Approve/Reject should be offered at all - true once the
   * session has an architecture to render a decision on (`stage ===
   * "architecture"`), regardless of the current `approvalStatus`: a
   * decision can always be revisited (re-approve after reject, or record
   * a second reviewer's sign-off), see `approve_run`/`reject_run` in
   * app/api/routes/requirements.py. */
  readonly canApprove: boolean
  /** Same "grey out, don't hide" role gate as `sendAllowed`, for the
   * `Reviewer` role `POST .../approve`/`.../reject` require. */
  readonly decisionAllowed: boolean
  readonly decisionDisabledReason?: string
  readonly onGenerateBreakdown: () => void
  /** Whether "Generate work breakdown" should be offered at all - only
   * true once the architecture has been approved and no breakdown exists
   * yet for this session, mirroring `canAccept`'s "only offer once it's
   * possible" shape one stage later (see
   * `app/api/routes/work_breakdown.py`'s `generate_work_breakdown`, which
   * 409s otherwise). */
  readonly canGenerateBreakdown: boolean
  readonly generateBreakdownLabel: string
  /** Same "grey out, don't hide" role gate as `acceptAllowed`, for the
   * `Architect` role `POST .../work-breakdown` requires. */
  readonly generateBreakdownAllowed: boolean
  readonly generateBreakdownDisabledReason?: string
  readonly onGenerateTechnicalDesign: () => void
  /** Whether "Generate technical design" should be offered at all - only
   * true once a work breakdown exists and no technical design document
   * exists yet for this session, the same "only offer once it's possible"
   * shape as `canGenerateBreakdown` one stage later (see
   * `app/api/routes/technical_design.py`'s `generate_technical_design`,
   * which 409s otherwise). */
  readonly canGenerateTechnicalDesign: boolean
  readonly generateTechnicalDesignLabel: string
  /** Same "grey out, don't hide" role gate as `generateBreakdownAllowed`,
   * for the `Architect` role `POST .../technical-design` requires. */
  readonly generateTechnicalDesignAllowed: boolean
  readonly generateTechnicalDesignDisabledReason?: string
  /** "pending" | "approved" | "rejected" - the session's current decision,
   * shown as a badge next to the buttons. Only meaningful when
   * `canApprove` is true. */
  readonly approvalStatus: string
  /** Whether the input/buttons should be interactive right now - false
   * while loading the initial session or while a request is in flight. */
  readonly canSend: boolean
  readonly placeholder: string
  /** The filename behind the current requirements version, if it came from
   * an uploaded file rather than typed text (`RequirementsRunView.source_filename`).
   * `null`/`undefined` shows nothing. */
  readonly sourceFilename?: string | null
}

/** The AI interaction layer: a chat transcript over the *current* artifact,
 * not a generator in its own right. Every entry here reflects something the
 * backend actually did (started a session, refined it, accepted it, or
 * rejected the request) - nothing here is fabricated conversational filler. */
export function Conversation({
  transcript,
  status,
  statusLabel,
  onSend,
  sendAllowed,
  sendDisabledReason,
  onSendFile,
  canUploadFile,
  hasRequirements,
  uploadAllowed,
  uploadDisabledReason,
  onAccept,
  canAccept,
  acceptLabel,
  acceptAllowed,
  acceptDisabledReason,
  onApprove,
  onReject,
  canApprove,
  decisionAllowed,
  decisionDisabledReason,
  onGenerateBreakdown,
  canGenerateBreakdown,
  generateBreakdownLabel,
  generateBreakdownAllowed,
  generateBreakdownDisabledReason,
  onGenerateTechnicalDesign,
  canGenerateTechnicalDesign,
  generateTechnicalDesignLabel,
  generateTechnicalDesignAllowed,
  generateTechnicalDesignDisabledReason,
  approvalStatus,
  canSend,
  placeholder,
  sourceFilename,
}: ConversationProps) {
  const [input, setInput] = useState("")
  /** The file staged via "Attach a file", not yet sent - lets the input be
   * text alone, a file alone, or both together. Cleared once actually
   * submitted (successfully or not - `onSendFile` itself handles/reports
   * failures, same as `onSend`). */
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // Sending with an attached file is gated by `uploadAllowed` (the `User`
  // role the upload routes require); text-only sending is gated by
  // `sendAllowed`. Whichever applies is what decides if Send is enabled.
  const activeSendAllowed = attachedFile ? uploadAllowed : sendAllowed
  const activeSendDisabledReason = attachedFile ? uploadDisabledReason : sendDisabledReason
  const hasContent = Boolean(input.trim()) || attachedFile !== null

  const handleSubmit = (event: React.SubmitEvent) => {
    event.preventDefault()
    if (!canSend || !hasContent || !activeSendAllowed) return
    const notes = input.trim()
    if (attachedFile) {
      onSendFile(attachedFile, notes || undefined)
      setAttachedFile(null)
    } else {
      onSend(notes)
    }
    setInput("")
  }

  const handleFileChosen = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    // Reset the input immediately so choosing the same file again (e.g.
    // after removing it) still fires a change event.
    event.target.value = ""
    if (!file) return
    // Stage it - the user still has to press Send. Any text already typed
    // stays put and goes along as notes.
    setAttachedFile(file)
  }

  const attachFileTitle = hasRequirements
    ? `Attach a file (${SUPPORTED_UPLOAD_EXTENSIONS.join(", ")}) - its content is merged into the current requirements, same as typing a refinement. An image is auto-detected as a document screenshot (merged as text) or a system design diagram (redrawn as an architecture directly)`
    : `Attach a file (${SUPPORTED_UPLOAD_EXTENSIONS.join(", ")}) instead of typing your requirements. An image is auto-detected as a document screenshot (processed as text) or a system design diagram (redrawn as an architecture directly)`
  const uploadButtonTitle = uploadAllowed ? attachFileTitle : uploadDisabledReason

  return (
    <div className="conversation">
      <div className="conversation-status">
        <span className={`status-pill status-${status}`}>{statusLabel}</span>
        {sourceFilename && (
          <span className="source-file-pill" title="Requirements were built from this attached file">
            Source: {sourceFilename}
          </span>
        )}
        {canApprove && (
          <span className={`approval-pill approval-${approvalStatus}`}>
            {approvalStatus === "approved" && "Approved"}
            {approvalStatus === "rejected" && "Rejected"}
            {approvalStatus === "pending" && "Pending approval"}
          </span>
        )}
      </div>

      <div className="transcript">
        {transcript.length === 0 && (
          <p className="muted">Describe what you want to build to get started.</p>
        )}
        {transcript.map((entry) => (
          <div
            key={entry.id}
            className={
              entry.tone === "error"
                ? `transcript-entry transcript-${entry.role} transcript-error`
                : `transcript-entry transcript-${entry.role}`
            }
          >
            {entry.content}
          </div>
        ))}
      </div>

      <form onSubmit={handleSubmit} className="conversation-input">
        {attachedFile && (
          <div className="attached-file-pill">
            <span>Attached: {attachedFile.name}</span>
            <button
              type="button"
              className="attached-file-remove"
              onClick={() => setAttachedFile(null)}
              disabled={!canSend}
              aria-label={`Remove attached file ${attachedFile.name}`}
              title="Remove attached file"
            >
              ×
            </button>
          </div>
        )}
        <textarea
          rows={3}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={placeholder}
          disabled={!canSend}
        />
        <div className="button-row">
          <button
            type="submit"
            className="button-sm"
            disabled={!canSend || !hasContent || !activeSendAllowed}
            title={!activeSendAllowed ? activeSendDisabledReason : undefined}
          >
            Send
          </button>
          {canUploadFile && !attachedFile && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept={SUPPORTED_UPLOAD_EXTENSIONS.join(",")}
                onChange={handleFileChosen}
                disabled={!canSend || !uploadAllowed}
                style={{ display: "none" }}
              />
              <button
                type="button"
                className="upload-button"
                onClick={() => fileInputRef.current?.click()}
                disabled={!canSend || !uploadAllowed}
                title={uploadButtonTitle}
              >
                Attach a file
              </button>
            </>
          )}
          {canAccept && (
            <button
              type="button"
              onClick={onAccept}
              disabled={!canSend || !acceptAllowed}
              title={!acceptAllowed ? acceptDisabledReason : undefined}
            >
              {acceptLabel}
            </button>
          )}
          {canApprove && (
            <>
              <button
                type="button"
                className="approve-button button-sm"
                onClick={onApprove}
                disabled={!canSend || approvalStatus === "approved" || !decisionAllowed}
                title={!decisionAllowed ? decisionDisabledReason : undefined}
              >
                Approve
              </button>
              <button
                type="button"
                className="reject-button button-sm"
                onClick={onReject}
                disabled={!canSend || approvalStatus === "rejected" || !decisionAllowed}
                title={!decisionAllowed ? decisionDisabledReason : undefined}
              >
                Reject
              </button>
            </>
          )}
          {canGenerateBreakdown && (
            <button
              type="button"
              onClick={onGenerateBreakdown}
              disabled={!canSend || !generateBreakdownAllowed}
              title={!generateBreakdownAllowed ? generateBreakdownDisabledReason : undefined}
            >
              {generateBreakdownLabel}
            </button>
          )}
          {canGenerateTechnicalDesign && (
            <button
              type="button"
              onClick={onGenerateTechnicalDesign}
              disabled={!canSend || !generateTechnicalDesignAllowed}
              title={
                !generateTechnicalDesignAllowed
                  ? generateTechnicalDesignDisabledReason
                  : undefined
              }
            >
              {generateTechnicalDesignLabel}
            </button>
          )}
        </div>
        {canUploadFile && (
          <p className="muted upload-hint">
            Supported file types: {SUPPORTED_UPLOAD_EXTENSIONS.join(", ")}
            {hasRequirements &&
              " - attaching a file merges its content into the current requirements, the same as typing a refinement above."}
          </p>
        )}
      </form>
    </div>
  )
}
