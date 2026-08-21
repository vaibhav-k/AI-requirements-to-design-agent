import { useEffect, useState } from "react"

import { describeError, useRequirementsApi } from "../api"
import { useVersionedArtifact } from "../hooks/useVersionedArtifact"
import { downloadSvgAsPng } from "../lib/exportDiagram"
import type {
  RequirementsArtifact,
  RequirementsRunView,
  SystemDesignArtifact,
  TechnicalDesignArtifact,
  WorkBreakdownArtifact,
} from "../types"
import { ArchitectureView } from "./ArchitectureView"
import { DiagramViewer } from "./DiagramViewer"
import { ErrorBanner } from "./ErrorBanner"
import { RequirementsEditor } from "./RequirementsEditor"
import { RequirementsView } from "./RequirementsView"
import { TechnicalDesignView } from "./TechnicalDesignView"
import { VersionBar } from "./VersionBar"
import { WorkBreakdownView } from "./WorkBreakdownView"

export type ArtifactTab =
  | "requirements"
  | "architecture"
  | "work_breakdown"
  | "technical_design"

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
  hasTechnicalDesign: boolean
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
  hasTechnicalDesign,
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
  const technicalDesignHistory = useVersionedArtifact<TechnicalDesignArtifact>({
    sessionId,
    refreshKey,
    listVersions: api.listTechnicalDesignVersions,
    getVersion: api.getTechnicalDesignVersion,
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

  const [docxExportError, setDocxExportError] = useState<string | null>(null)
  const [exportingDocx, setExportingDocx] = useState(false)

  const handleExportDocx = () => {
    setDocxExportError(null)
    setExportingDocx(true)
    api
      .exportTechnicalDesignDocx(sessionId)
      .catch((err: unknown) => {
        setDocxExportError(
          `Could not export the technical design document: ${describeError(err)}`,
        )
      })
      .finally(() => setExportingDocx(false))
  }

  // The architecture-generation phase always renders two complementary
  // diagrams (see README) - the technology-agnostic Logical Architecture
  // Diagram and the Azure Service Mapping Diagram - so this tab toggles
  // between the two rather than only ever showing one.
  const [diagramKind, setDiagramKind] = useState<"logical" | "azure">("logical")
  const [diagram, setDiagram] = useState<string | null>(null)
  const [diagramError, setDiagramError] = useState<string | null>(null)

  useEffect(() => {
    if (tab !== "architecture" || architectureHistory.selected === null) {
      return
    }
    let cancelled = false
    setDiagram(null)
    setDiagramError(null)
    const fetchDiagram =
      diagramKind === "logical" ? api.getArchitectureDiagram : api.getAzureMappingDiagram
    fetchDiagram(sessionId, architectureHistory.selected)
      .then((svg) => {
        if (!cancelled) setDiagram(svg)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        const label = diagramKind === "logical" ? "Logical Architecture" : "Azure Service Mapping"
        setDiagramError(`Could not load the ${label} diagram: ${describeError(err)}`)
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, tab, architectureHistory.selected, diagramKind, api])

  const [diagramDownloadError, setDiagramDownloadError] = useState<string | null>(null)

  const handleDownloadDiagramPng = () => {
    if (!diagram) return
    setDiagramDownloadError(null)
    const suffix = diagramKind === "logical" ? "logical" : "azure-mapping"
    const version = architectureHistory.selected ?? "latest"
    downloadSvgAsPng(diagram, `architecture-v${version}-${suffix}.png`, {
      onError: setDiagramDownloadError,
    })
  }

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
        <button
          type="button"
          className={tab === "technical_design" ? "tab active" : "tab"}
          disabled={!hasWorkBreakdown}
          onClick={() => setTab("technical_design")}
        >
          Technical Design
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
                  <div className="tab-row diagram-kind-row">
                    <button
                      type="button"
                      className={diagramKind === "logical" ? "tab active" : "tab"}
                      onClick={() => setDiagramKind("logical")}
                    >
                      Logical Architecture
                    </button>
                    <button
                      type="button"
                      className={diagramKind === "azure" ? "tab active" : "tab"}
                      onClick={() => setDiagramKind("azure")}
                    >
                      Azure Service Mapping
                    </button>
                  </div>
                  {diagramError && <ErrorBanner message={diagramError} />}
                  {diagramDownloadError && <ErrorBanner message={diagramDownloadError} />}
                  {diagram && (
                    <DiagramViewer
                      svg={diagram}
                      onInspect={setHighlighted}
                      onDownloadPng={handleDownloadDiagramPng}
                    />
                  )}
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

      {tab === "technical_design" &&
        (!hasWorkBreakdown ? (
          <p className="muted">
            The work breakdown must exist before a technical design document can be
            generated.
          </p>
        ) : !hasTechnicalDesign ? (
          <p className="muted">
            No technical design document generated yet - use "Generate technical
            design" in the conversation once the work breakdown exists.
          </p>
        ) : (
          <>
            <div className="panel-header">
              <VersionBar
                versions={technicalDesignHistory.versions}
                selected={technicalDesignHistory.selected}
                onSelect={technicalDesignHistory.setSelected}
                compareWith={technicalDesignHistory.compareWith}
                onCompareChange={technicalDesignHistory.setCompareWith}
                latestVersion={technicalDesignHistory.versions.at(-1) ?? null}
              />
              <button type="button" onClick={handleExportDocx} disabled={exportingDocx}>
                {exportingDocx ? "Exporting…" : "Export DOCX"}
              </button>
            </div>
            {docxExportError && (
              <ErrorBanner
                message={docxExportError}
                onDismiss={() => setDocxExportError(null)}
              />
            )}
            {technicalDesignHistory.error && (
              <ErrorBanner message={technicalDesignHistory.error} />
            )}
            {technicalDesignHistory.loading && !technicalDesignHistory.data && (
              <p className="muted">Loading…</p>
            )}
            {technicalDesignHistory.data && technicalDesignHistory.compareData && (
              <p className="muted">
                Comparing v{technicalDesignHistory.compareWith} (below) against v
                {technicalDesignHistory.selected} (above) - side-by-side diffing isn't
                supported for technical design documents yet.
              </p>
            )}
            {technicalDesignHistory.data && (
              <TechnicalDesignView data={technicalDesignHistory.data} />
            )}
            {technicalDesignHistory.compareData && (
              <TechnicalDesignView data={technicalDesignHistory.compareData} />
            )}
          </>
        ))}
    </div>
  )
}
