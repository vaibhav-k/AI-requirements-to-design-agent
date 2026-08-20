import { useEffect, useState } from "react"

import { describeError, useRequirementsApi } from "../api"
import { useVersionedArtifact } from "../hooks/useVersionedArtifact"
import type {
  RequirementsArtifact,
  RequirementsRunView,
  SystemDesignArtifact,
  WorkBreakdownArtifact,
} from "../types"
import { ArchitectureView } from "./ArchitectureView"
import { DiagramViewer } from "./DiagramViewer"
import { ErrorBanner } from "./ErrorBanner"
import { RequirementsEditor } from "./RequirementsEditor"
import { RequirementsView } from "./RequirementsView"
import { VersionBar } from "./VersionBar"
import { WorkBreakdownView } from "./WorkBreakdownView"

export type ArtifactTab = "requirements" | "architecture" | "work_breakdown"

interface ArtifactPanelProps {
  sessionId: string
  /** Bumped whenever the conversation just persisted a new version, so the
   * version lists here re-fetch instead of silently going stale. */
  refreshKey: number
  hasRequirements: boolean
  hasArchitecture: boolean
  /** Whether the session's *current* architecture has been approved
   * (`RequirementsRunView.approval_status === "approved"`) - the Work
   * Breakdown tab stays disabled until then, mirroring the Architecture
   * tab's `!hasArchitecture` gate one stage later (see
   * `app/api/routes/work_breakdown.py`'s `_require_architecture_approved`). */
  architectureApproved: boolean
  hasWorkBreakdown: boolean
  /** Which tab is shown. Lifted up to Workspace rather than kept as local
   * state here, so Workspace can switch to the Architecture tab itself the
   * moment `accept` persists a design - see Workspace.tsx's handleAccept. */
  activeTab: ArtifactTab
  onTabChange: (tab: ArtifactTab) => void
  /** The session's *current* requirements (`run.requirements` in
   * Workspace.tsx), for `RequirementsEditor` - deliberately independent of
   * whichever version the history selector below happens to be showing,
   * since editing always replaces the session's live requirements. */
  currentRequirements: RequirementsArtifact | null
  onRequirementsSaved: (result: RequirementsRunView) => void
  editRequirementsAllowed: boolean
  editRequirementsDisabledReason?: string
}

/** The artifact-explorer half of the workspace: renders exactly what's
 * persisted for the selected version (and, when a compare version is also
 * selected, a side-by-side field diff) - this component never generates or
 * guesses content, only fetches and displays it. */
export function ArtifactPanel({
  sessionId,
  refreshKey,
  hasRequirements,
  hasArchitecture,
  architectureApproved,
  hasWorkBreakdown,
  activeTab: tab,
  onTabChange: setTab,
  currentRequirements,
  onRequirementsSaved,
  editRequirementsAllowed,
  editRequirementsDisabledReason,
}: ArtifactPanelProps) {
  const api = useRequirementsApi()
  const [highlighted, setHighlighted] = useState<string | null>(null)

  const requirementsHistory = useVersionedArtifact<RequirementsArtifact>({
    sessionId,
    refreshKey,
    listVersions: api.listRequirementsVersions,
    getVersion: api.getRequirementsVersion,
  })
  const architectureHistory = useVersionedArtifact<SystemDesignArtifact>({
    sessionId,
    refreshKey,
    listVersions: api.listArchitectureVersions,
    getVersion: api.getArchitectureVersion,
  })
  const workBreakdownHistory = useVersionedArtifact<WorkBreakdownArtifact>({
    sessionId,
    refreshKey,
    listVersions: api.listWorkBreakdownVersions,
    getVersion: api.getWorkBreakdownVersion,
  })

  const [exportError, setExportError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const handleExportCsv = () => {
    setExportError(null)
    setExporting(true)
    api
      .exportWorkBreakdownCsv(sessionId)
      .catch((err: unknown) => {
        setExportError(`Could not export the work breakdown: ${describeError(err)}`)
      })
      .finally(() => setExporting(false))
  }

  const [diagram, setDiagram] = useState<string | null>(null)
  const [diagramError, setDiagramError] = useState<string | null>(null)

  useEffect(() => {
    if (tab !== "architecture" || architectureHistory.selected === null) {
      return
    }
    let cancelled = false
    setDiagram(null)
    setDiagramError(null)
    api
      .getArchitectureDiagram(sessionId, architectureHistory.selected)
      .then((svg) => {
        if (!cancelled) setDiagram(svg)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setDiagramError(`Could not load the diagram: ${describeError(err)}`)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, tab, architectureHistory.selected, api])

  return (
    <div className="artifact-panel">
      <div className="tab-row">
        <button
          type="button"
          className={tab === "requirements" ? "tab active" : "tab"}
          onClick={() => setTab("requirements")}
        >
          Requirements
        </button>
        <button
          type="button"
          className={tab === "architecture" ? "tab active" : "tab"}
          disabled={!hasArchitecture}
          onClick={() => setTab("architecture")}
        >
          Architecture
        </button>
        <button
          type="button"
          className={tab === "work_breakdown" ? "tab active" : "tab"}
          disabled={!architectureApproved}
          onClick={() => setTab("work_breakdown")}
        >
          Task Planning
        </button>
      </div>

      {tab === "requirements" && (
        <RequirementsEditor
          sessionId={sessionId}
          requirements={currentRequirements}
          editAllowed={editRequirementsAllowed}
          editDisabledReason={editRequirementsDisabledReason}
          onSaved={onRequirementsSaved}
        />
      )}

      {tab === "requirements" &&
        (!hasRequirements ? (
          <p className="muted">
            No requirements yet - describe what you want to build in the conversation.
          </p>
        ) : (
          <>
            <VersionBar
              versions={requirementsHistory.versions}
              selected={requirementsHistory.selected}
              onSelect={requirementsHistory.setSelected}
              compareWith={requirementsHistory.compareWith}
              onCompareChange={requirementsHistory.setCompareWith}
              latestVersion={requirementsHistory.versions.at(-1) ?? null}
            />
            {requirementsHistory.error && <ErrorBanner message={requirementsHistory.error} />}
            {requirementsHistory.loading && !requirementsHistory.data && (
              <p className="muted">Loading…</p>
            )}
            {requirementsHistory.data && (
              <RequirementsView
                data={requirementsHistory.data}
                compareData={requirementsHistory.compareData}
              />
            )}
          </>
        ))}

      {tab === "architecture" &&
        (!hasArchitecture ? (
          <p className="muted">
            No architecture generated yet - accept the requirements to generate one.
          </p>
        ) : (
          <>
            <VersionBar
              versions={architectureHistory.versions}
              selected={architectureHistory.selected}
              onSelect={architectureHistory.setSelected}
              compareWith={architectureHistory.compareWith}
              onCompareChange={architectureHistory.setCompareWith}
              latestVersion={architectureHistory.versions.at(-1) ?? null}
            />
            {architectureHistory.error && <ErrorBanner message={architectureHistory.error} />}
            {architectureHistory.loading && !architectureHistory.data && (
              <p className="muted">Loading…</p>
            )}
            {architectureHistory.data && (
              <div className="architecture-layout">
                <ArchitectureView
                  data={architectureHistory.data}
                  compareData={architectureHistory.compareData}
                  highlightedComponentId={highlighted}
                />
                <div className="diagram-column">
                  {diagramError && <ErrorBanner message={diagramError} />}
                  {diagram && <DiagramViewer svg={diagram} onInspect={setHighlighted} />}
                  {!diagram && !diagramError && <p className="muted">Loading diagram…</p>}
                </div>
              </div>
            )}
          </>
        ))}

      {tab === "work_breakdown" &&
        (!architectureApproved ? (
          <p className="muted">
            The architecture must be approved before a work breakdown can be generated.
          </p>
        ) : !hasWorkBreakdown ? (
          <p className="muted">
            No work breakdown generated yet - use "Generate work breakdown" in the conversation
            once the architecture is approved.
          </p>
        ) : (
          <>
            <div className="panel-header">
              <VersionBar
                versions={workBreakdownHistory.versions}
                selected={workBreakdownHistory.selected}
                onSelect={workBreakdownHistory.setSelected}
                compareWith={workBreakdownHistory.compareWith}
                onCompareChange={workBreakdownHistory.setCompareWith}
                latestVersion={workBreakdownHistory.versions.at(-1) ?? null}
              />
              <button type="button" onClick={handleExportCsv} disabled={exporting}>
                {exporting ? "Exporting…" : "Export CSV"}
              </button>
            </div>
            {exportError && <ErrorBanner message={exportError} onDismiss={() => setExportError(null)} />}
            {workBreakdownHistory.error && <ErrorBanner message={workBreakdownHistory.error} />}
            {workBreakdownHistory.loading && !workBreakdownHistory.data && (
              <p className="muted">Loading…</p>
            )}
            {workBreakdownHistory.data && workBreakdownHistory.compareData && (
              <p className="muted">
                Comparing v{workBreakdownHistory.compareWith} (below) against v
                {workBreakdownHistory.selected} (above) - side-by-side diffing isn't supported for
                work breakdowns yet.
              </p>
            )}
            {workBreakdownHistory.data && <WorkBreakdownView data={workBreakdownHistory.data} />}
            {workBreakdownHistory.compareData && (
              <WorkBreakdownView data={workBreakdownHistory.compareData} />
            )}
          </>
        ))}
    </div>
  )
}
