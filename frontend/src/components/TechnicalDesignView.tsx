import type { DesignSection, TechnicalDesignArtifact } from "../types"

interface TechnicalDesignViewProps {
  data: TechnicalDesignArtifact
}

// Section heading levels are 1-3 (see app/domain/technical_design.py's
// `MAX_SECTION_LEVEL`) - mapped straight onto h2/h3/h4 so the document
// title above (rendered as h1 by ArtifactPanel/Workspace, same as every
// other artifact view) stays the single top-level heading on the page.
const HEADING_TAGS = ["h2", "h3", "h4"] as const

function SectionHeading({ section }: { section: DesignSection }) {
  const Tag = HEADING_TAGS[Math.max(1, Math.min(section.level, 3)) - 1]
  return <Tag>{section.title}</Tag>
}

/** Renders one flat `DesignSection` - prose body, bullets, numbered
 * steps, and an optional table, in that order, matching the order
 * `backend/tools-service/src/infrastructure/document_export.py` renders
 * them into the exported `.docx`, so the on-screen preview and the
 * downloaded file read the same way. */
function Section({ section }: { section: DesignSection }) {
  return (
    <div className="td-section">
      <SectionHeading section={section} />
      {section.body
        .split("\n")
        .filter((line) => line.trim().length > 0)
        .map((line, index) => <p key={index}>{line}</p>)}
      {section.bullets.length > 0 && (
        <ul>
          {section.bullets.map((bullet, index) => (
            <li key={index}>{bullet}</li>
          ))}
        </ul>
      )}
      {section.numbered_steps.length > 0 && (
        <ol>
          {section.numbered_steps.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      )}
      {section.table && section.table.rows.length > 0 && (
        <table className="td-table">
          {section.table.headers.length > 0 && (
            <thead>
              <tr>
                {section.table.headers.map((header, index) => (
                  <th key={index}>{header}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {section.table.rows.map((row, rowIndex) => (
              <tr key={rowIndex}>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex}>{cell}</td>
                ))}
              </tr>
            ))}
          </tbody>
          {section.table.caption && (
            <caption>{section.table.caption}</caption>
          )}
        </table>
      )}
      {section.include_diagram && (
        <p className="muted">
          [The approved architecture diagram is embedded here in the exported
          .docx.]
        </p>
      )}
    </div>
  )
}

/** Renders the persisted technical design document exactly as stored -
 * this component never generates or reorders content, same as
 * WorkBreakdownView/ArchitectureView/RequirementsView. The actual
 * downloadable `.docx` (with the diagram + traceability appendices
 * rendered by `backend/tools-service`) comes from
 * `api.exportTechnicalDesignDocx`, not from this preview. */
export function TechnicalDesignView({ data }: TechnicalDesignViewProps) {
  return (
    <div className="technical-design-view">
      <h1>{data.document_title}</h1>
      {data.system_name && <p className="muted">{data.system_name}</p>}
      {data.version && <p className="muted">Version {data.version}</p>}

      {data.executive_summary && (
        <div className="td-section">
          <h2>Executive Summary</h2>
          {data.executive_summary
            .split("\n")
            .filter((line) => line.trim().length > 0)
            .map((line, index) => <p key={index}>{line}</p>)}
        </div>
      )}

      {data.sections.length === 0 ? (
        <p className="muted">No sections yet.</p>
      ) : (
        data.sections.map((section, index) => (
          <Section key={index} section={section} />
        ))
      )}
    </div>
  )
}
