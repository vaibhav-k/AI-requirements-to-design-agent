import type { WorkBreakdownArtifact } from "../types"

interface WorkBreakdownViewProps {
  data: WorkBreakdownArtifact
}

/** A task's requirement/architecture traceability tags - every task must
 * carry at least one of these (see app/domain/work_breakdown.py's
 * `WorkBreakdownTask` docstring), rendered as `<code>` tags the same way
 * every other artifact view in this app shows an id. */
function TraceabilityTags({
  requirementIds,
  architectureIds,
}: {
  requirementIds: string[]
  architectureIds: string[]
}) {
  if (requirementIds.length === 0 && architectureIds.length === 0) {
    return null
  }
  return (
    <span className="traceability-tags">
      {requirementIds.map((id) => (
        <code key={`req-${id}`}>{id}</code>
      ))}
      {architectureIds.map((id) => (
        <code key={`arch-${id}`}>{id}</code>
      ))}
    </span>
  )
}

/** Renders the persisted Feature -> Story -> Task hierarchy exactly as
 * stored - this component never generates or reorders content, same as
 * ArchitectureView/RequirementsView. */
export function WorkBreakdownView({ data }: WorkBreakdownViewProps) {
  return (
    <div className="work-breakdown-view">
      {data.features.length === 0 ? (
        <p className="muted">No features yet.</p>
      ) : (
        data.features.map((feature) => (
          <div key={feature.feature} className="wb-feature">
            <h3>{feature.feature}</h3>
            {feature.stories.map((story) => (
              <div key={story.story} className="wb-story">
                <h4>{story.story}</h4>
                <ul>
                  {story.tasks.map((task) => (
                    <li key={task.task}>
                      <strong>{task.task}</strong>{" "}
                      <span className="domain-badge">{task.effort}</span>
                      <p>{task.description}</p>
                      <TraceabilityTags
                        requirementIds={task.requirement_ids}
                        architectureIds={task.architecture_ids}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        ))
      )}

      <h3>Ambiguities</h3>
      {data.ambiguities.length > 0 ? (
        <ul className="ambiguities-list">
          {data.ambiguities.map((ambiguity, index) => (
            <li key={index}>
              <span className="domain-badge">{ambiguity.kind}</span> {ambiguity.description}
              {ambiguity.related_ids.length > 0 && (
                <>
                  {" "}
                  {ambiguity.related_ids.map((id) => (
                    <code key={id}>{id}</code>
                  ))}
                </>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}
    </div>
  )
}
