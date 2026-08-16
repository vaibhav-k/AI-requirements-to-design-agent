import { useState } from "react"

export interface TranscriptEntry {
  id: string
  role: "user" | "assistant"
  content: string
  tone?: "error"
}

export type ConversationStatus = "idle" | "loading" | "processing" | "ready" | "error"

interface ConversationProps {
  transcript: TranscriptEntry[]
  status: ConversationStatus
  statusLabel: string
  onSend: (input: string) => void
  onAccept: () => void
  /** Whether "Accept & generate architecture" should be offered at all —
   * only true once there are requirements to accept and the session hasn't
   * already moved past the requirements stage. */
  canAccept: boolean
  acceptLabel: string
  /** Whether the input/buttons should be interactive right now — false
   * while loading the initial session or while a request is in flight. */
  canSend: boolean
  placeholder: string
}

/** The AI interaction layer: a chat transcript over the *current* artifact,
 * not a generator in its own right. Every entry here reflects something the
 * backend actually did (started a session, refined it, accepted it, or
 * rejected the request) — nothing here is fabricated conversational filler. */
export function Conversation({
  transcript,
  status,
  statusLabel,
  onSend,
  onAccept,
  canAccept,
  acceptLabel,
  canSend,
  placeholder,
}: ConversationProps) {
  const [input, setInput] = useState("")

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!input.trim() || !canSend) return
    onSend(input.trim())
    setInput("")
  }

  return (
    <div className="conversation">
      <div className="conversation-status">
        <span className={`status-pill status-${status}`}>{statusLabel}</span>
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
        <textarea
          rows={3}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={placeholder}
          disabled={!canSend}
        />
        <div className="button-row">
          <button type="submit" disabled={!canSend || !input.trim()}>
            Send
          </button>
          {canAccept && (
            <button type="button" onClick={onAccept} disabled={!canSend}>
              {acceptLabel}
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
