import { useEffect, useState } from "react"

import { describeError, useRequirementsApi } from "../api"
import { useVersionedArtifact } from "../hooks/useVersionedArtifact"
import type { RequirementsArtifact, SystemDesignArtifact } from "../types"
import { ArchitectureView } from "./ArchitectureView"
import { DiagramViewer } from "./DiagramViewer"
import { ErrorBanner } from "./ErrorBanner"
import { RequirementsView } from "./RequirementsView"
import { VersionBar } from "./VersionBar"

export type ArtifactTab = "requirements" | "architecture"

interface ArtifactPanelProps {
  sessionId: string
  /** Bumped whenever the conversation just persisted a new version, so the
   * version lists here re-fetch instead of silently going stale. */
  refreshKey: number
  hasRequirements: boolean
  hasArchitecture: boolean
  /** Which tab is shown. Lifted up to Workspace rather than kept as local
   * state here, so Workspace can switch to the Architecture tab itself the
   * moment `accept` persists a design — see Workspace.tsx's handleAccept. */
  activeTab: ArtifactTab
  onTabChange: (tab: ArtifactTab) => void
}

/** The artifact-explorer half of the workspace: renders exactly what's
 * persisted for the selected version (and, when a compare version is also
 * selected, a side-by-side field diff) — this component never generates or
 * guesses content, only fetches and displays it. */
export function ArtifactPanel({
  sessionId,
  refreshKey,
  hasRequirements,
  hasArchitecture,
  activeTab: tab,
  onTabChange: setTab,
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
      </div>

      {tab === "requirements" &&
        (!hasRequirements ? (
          <p className="muted">
            No requirements yet — describe what you want to build in the conversation.
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
            No architecture generated yet — accept the requirements to generate one.
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
    </div>
  )
}
