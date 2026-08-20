import { useEffect, useState } from "react"

import { describeError, friendlyErrorMessage, useRequirementsApi } from "../api"
import type { ManualRequirementInput, RequirementsArtifact, RequirementsRunView } from "../types"
import { ErrorBanner } from "./ErrorBanner"

/** Exact placeholder text `app/api/routes/requirements.py`'s
 * `_stub_requirements_from_diagram` sets on `business_goal` for a session
 * that started from an uploaded diagram image rather than typed
 * requirements - matched verbatim so this editor (and Workspace.tsx's
 * transcript message after a diagram upload) can call the situation out
 * explicitly instead of showing the raw placeholder unexplained. Exported
 * so both places check the exact same string rather than each hand-typing
 * their own copy that could drift out of sync with the backend or with
 * each other. */
export const DIAGRAM_STUB_BUSINESS_GOAL =
  "Not specified - this session started from a diagram upload instead of typed requirements."

interface DraftRequirement {
  description: string
  priority: string
  rationale: string
}

function toDrafts(items: { description: string; priority: string; rationale: string | null }[]): DraftRequirement[] {
  return items.map((item) => ({
    description: item.description,
    priority: item.priority,
    rationale: item.rationale ?? "",
  }))
}

function toManualInputs(items: DraftRequirement[]): ManualRequirementInput[] {
  return items.map((item) => ({
    description: item.description,
    priority: item.priority,
    rationale: item.rationale.trim() || null,
  }))
}

/** One "current list + inline add form" editor, shared by the functional
 * and non-functional requirement lists below - the backend treats each
 * list as a full replacement (see `edit_requirements`'s docstring), so this
 * only ever mutates the full in-memory list; nothing is sent to the
 * backend until the surrounding form's "Save requirements" is clicked. */
function RequirementListEditor({
  label,
  items,
  onChange,
  disabled,
}: {
  label: string
  items: DraftRequirement[]
  onChange: (items: DraftRequirement[]) => void
  disabled: boolean
}) {
  const [description, setDescription] = useState("")
  // Empty by default rather than defaulting to "medium" - priority is a
  // real judgment call the person filling this in has to make, not
  // something safe to silently assume; `handleAdd`/the "+ Add requirement"
  // button below both treat an empty selection the same as an empty
  // description, refusing to add until both are set.
  const [priority, setPriority] = useState("")
  const [rationale, setRationale] = useState("")

  const canAdd = description.trim().length > 0 && priority.length > 0

  const handleAdd = () => {
    const trimmed = description.trim()
    if (!trimmed || !priority) return
    onChange([...items, { description: trimmed, priority, rationale: rationale.trim() }])
    setDescription("")
    setPriority("")
    setRationale("")
  }

  return (
    <div className="requirement-list-editor">
      <h4>{label}</h4>
      {items.length === 0 ? (
        <p className="muted">None.</p>
      ) : (
        <ul>
          {items.map((item, index) => (
            <li key={index}>
              <strong>[{item.priority}]</strong> {item.description}
              {item.rationale && <span className="muted"> - {item.rationale}</span>}{" "}
              <button
                type="button"
                className="requirement-remove-button"
                disabled={disabled}
                onClick={() => onChange(items.filter((_, i) => i !== index))}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="requirement-add-form">
        <input
          type="text"
          placeholder="Description"
          value={description}
          disabled={disabled}
          onChange={(event) => setDescription(event.target.value)}
        />
        <select value={priority} disabled={disabled} onChange={(event) => setPriority(event.target.value)}>
          <option value="" disabled>
            Select priority...
          </option>
          <option value="high">high</option>
          <option value="medium">medium</option>
          <option value="low">low</option>
        </select>
        <input
          type="text"
          placeholder="Rationale (optional)"
          value={rationale}
          disabled={disabled}
          onChange={(event) => setRationale(event.target.value)}
        />
        <button type="button" disabled={disabled || !canAdd} onClick={handleAdd}>
          + Add requirement
        </button>
      </div>
    </div>
  )
}

interface RequirementsEditorProps {
  sessionId: string
  /** The session's *current* requirements (`run.requirements` in
   * Workspace.tsx) - deliberately not whatever version `ArtifactPanel`'s
   * version selector happens to be showing, since a save here always
   * replaces the session's live requirements, not some past version. */
  requirements: RequirementsArtifact | null
  editAllowed: boolean
  editDisabledReason?: string
  onSaved: (result: RequirementsRunView) => void
}

/** Manual, non-AI requirements editor - the client for `PUT
 * .../requirements` (`app/api/routes/requirements.py`'s `edit_requirements`).
 * Exists mainly to unblock a diagram-originated session (empty functional/
 * non-functional requirements, since a diagram gives no real basis to
 * invent any) from ever generating a work breakdown, but works from any
 * session stage, not just while `stage === "requirements"` - unlike the
 * chat-based "Refine" flow in Conversation.tsx.
 *
 * Owns its own API call and error state (the same "panel-local simple
 * mutation" shape ArtifactPanel's CSV export already uses) rather than
 * routing through Workspace's handlers, since nothing here needs the
 * conversation transcript to narrate intermediate progress - only the
 * final, already-successful result is handed back via `onSaved`.
 */
export function RequirementsEditor({
  sessionId,
  requirements,
  editAllowed,
  editDisabledReason,
  onSaved,
}: RequirementsEditorProps) {
  const api = useRequirementsApi()
  // A diagram-originated session's `business_goal` is always the exact
  // `DIAGRAM_STUB_BUSINESS_GOAL` placeholder, but its `summary` isn't - it's
  // `_stub_requirements_from_diagram`'s own generated text plus the
  // interpreted architecture summary appended, so it can't be matched
  // verbatim the same way. Once `business_goal` proves the whole artifact is
  // placeholder/derived rather than authored, though, `summary` is exactly
  // as fabricated - so both start blank here, with placeholder text standing
  // in for them instead of pre-filling the textarea with generated prose
  // that reads like a real answer but isn't one.
  const isDiagramStub = requirements?.business_goal === DIAGRAM_STUB_BUSINESS_GOAL
  const [businessGoal, setBusinessGoal] = useState(isDiagramStub ? "" : requirements?.business_goal ?? "")
  const [summary, setSummary] = useState(isDiagramStub ? "" : requirements?.summary ?? "")
  const [functional, setFunctional] = useState<DraftRequirement[]>(
    toDrafts(requirements?.functional_requirements ?? []),
  )
  const [nonFunctional, setNonFunctional] = useState<DraftRequirement[]>(
    toDrafts(requirements?.non_functional_requirements ?? []),
  )
  const [expanded, setExpanded] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const hasNoRequirements = functional.length === 0 && nonFunctional.length === 0

  // Reseed every draft field whenever the session changes, or a save (here
  // or elsewhere - e.g. a chat "Refine") hands back fresh requirements -
  // never on every keystroke, since `requirements` itself doesn't change
  // as this form is edited locally.
  useEffect(() => {
    setBusinessGoal(isDiagramStub ? "" : requirements?.business_goal ?? "")
    setSummary(isDiagramStub ? "" : requirements?.summary ?? "")
    setFunctional(toDrafts(requirements?.functional_requirements ?? []))
    setNonFunctional(toDrafts(requirements?.non_functional_requirements ?? []))
    setError(null)
  }, [sessionId, requirements, isDiagramStub])

  const handleSave = () => {
    setSaving(true)
    setError(null)
    api
      .editRequirements(sessionId, {
        business_goal: businessGoal,
        summary,
        functional_requirements: toManualInputs(functional),
        non_functional_requirements: toManualInputs(nonFunctional),
      })
      .then((result) => {
        onSaved(result)
        setExpanded(false)
      })
      .catch((err: unknown) => {
        setError(friendlyErrorMessage(err, `Could not save requirements: ${describeError(err)}`))
      })
      .finally(() => setSaving(false))
  }

  // Shown whenever there's nothing to generate a work breakdown from yet
  // (the diagram-stuck case this route exists for) - otherwise collapsed
  // behind an explicit toggle, since most sessions already have real,
  // AI-derived requirements that don't need a manual editor open by
  // default.
  const showForm = expanded || hasNoRequirements
  const disabled = !editAllowed || saving

  return (
    <div className="requirements-editor">
      {isDiagramStub && (
        <p className="muted diagram-hint">
          This session started from a diagram upload - add requirements here to enable Task
          Planning.
        </p>
      )}
      <div className="panel-header">
        <h3>Edit requirements</h3>
        {!showForm && (
          <button
            type="button"
            onClick={() => setExpanded(true)}
            disabled={!editAllowed}
            title={!editAllowed ? editDisabledReason : undefined}
          >
            {hasNoRequirements ? "Add requirements" : "Edit requirements"}
          </button>
        )}
      </div>
      {showForm && (
        <>
          {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
          <label>
            Business goal
            <textarea
              rows={2}
              value={businessGoal}
              disabled={disabled}
              placeholder="What business problem is this system solving?"
              onChange={(event) => setBusinessGoal(event.target.value)}
            />
          </label>
          <label>
            Summary
            <textarea
              rows={2}
              value={summary}
              disabled={disabled}
              placeholder="A short description of what this system does."
              onChange={(event) => setSummary(event.target.value)}
            />
          </label>
          <RequirementListEditor
            label="Functional requirements"
            items={functional}
            onChange={setFunctional}
            disabled={disabled}
          />
          <RequirementListEditor
            label="Non-functional requirements"
            items={nonFunctional}
            onChange={setNonFunctional}
            disabled={disabled}
          />
          <div className="button-row">
            <button
              type="button"
              onClick={handleSave}
              disabled={disabled}
              title={!editAllowed ? editDisabledReason : undefined}
            >
              {saving ? "Saving…" : "Save requirements"}
            </button>
            {!hasNoRequirements && (
              <button type="button" onClick={() => setExpanded(false)} disabled={saving}>
                Cancel
              </button>
            )}
          </div>
        </>
      )}
    </div>
  )
}
