import { diffByKey } from "../lib/diff"
import type { SystemDesignArtifact } from "../types"
import { DiffList } from "./DiffList"

interface ArchitectureViewProps {
  data: SystemDesignArtifact
  compareData?: SystemDesignArtifact | null
  /** Component id to highlight (from clicking a node in the diagram). */
  highlightedComponentId?: string | null
}

function ArchitectureSummary({ before, after }: { before?: string; after: string }) {
  const changed = before !== undefined && before !== after
  if (!changed) {
    return <p>{after}</p>
  }
  return (
    <p>
      <span className="diff-before-inline">{before}</span>
      {" → "}
      <span className="diff-after-inline">{after}</span>
    </p>
  )
}

/** Requirement ID → every component/interface that traces back to it,
 * built from the artifact's own `requirement_ids` fields - never invented,
 * only reorganized for display. */
function buildTraceability(data: SystemDesignArtifact): Map<string, string[]> {
  const trace = new Map<string, string[]>()
  const add = (reqId: string, label: string) => {
    const existing = trace.get(reqId) ?? []
    existing.push(label)
    trace.set(reqId, existing)
  }
  for (const component of data.components) {
    for (const reqId of component.requirement_ids) {
      add(reqId, `Component: ${component.name}`)
    }
  }
  for (const iface of data.interfaces) {
    for (const reqId of iface.requirement_ids) {
      add(reqId, `Interface: ${iface.name}`)
    }
  }
  return trace
}

export function ArchitectureView({
  data,
  compareData,
  highlightedComponentId,
}: ArchitectureViewProps) {
  const diffing = Boolean(compareData)
  const traceability = buildTraceability(data)

  return (
    <div className="architecture-view">
      <ArchitectureSummary
        before={compareData?.architecture_summary}
        after={data.architecture_summary}
      />

      <h3>Components</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(compareData!.components, data.components, (c) => c.id)}
          keyOf={(c) => c.id}
          emptyLabel="None."
          renderItem={(c) => (
            <>
              <code>{c.id}</code> <strong>{c.name}</strong>
              {c.domain && <span className="domain-badge">{c.domain}</span>} -{" "}
              {c.responsibility}
              {c.trust_zone && c.trust_zone !== "TBD" && (
                <span className="muted"> (Zone: {c.trust_zone})</span>
              )}
            </>
          )}
        />
      ) : (
        <ul>
          {data.components.map((c) => (
            <li
              key={c.id}
              className={c.id === highlightedComponentId ? "highlighted" : undefined}
            >
              <code>{c.id}</code> <strong>{c.name}</strong>
              {c.domain && <span className="domain-badge">{c.domain}</span>} -{" "}
              {c.responsibility}
              {c.trust_zone && c.trust_zone !== "TBD" && (
                <span className="muted"> (Zone: {c.trust_zone})</span>
              )}
            </li>
          ))}
        </ul>
      )}

      <h3>Actors</h3>
      {data.actors.length > 0 ? (
        <ul>
          {data.actors.map((actor) => (
            <li key={actor.id}>
              <code>{actor.id}</code> <strong>{actor.name}</strong>{" "}
              <span className="domain-badge">{actor.kind}</span> - {actor.description}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}

      <h3>Interfaces</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(compareData!.interfaces, data.interfaces, (i) => i.id)}
          keyOf={(i) => i.id}
          emptyLabel="None."
          renderItem={(iface) => (
            <>
              <code>{iface.id}</code> <strong>{iface.name}</strong>:{" "}
              {iface.source_component} → {iface.target_component} ({iface.flow_type}) -{" "}
              {iface.purpose}
            </>
          )}
        />
      ) : data.interfaces.length > 0 ? (
        <ul>
          {data.interfaces.map((iface) => (
            <li key={iface.id}>
              <code>{iface.id}</code> <strong>{iface.name}</strong>:{" "}
              {iface.source_component} → {iface.target_component} ({iface.flow_type}) -{" "}
              {iface.purpose}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}

      <h3>External dependencies</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(
            compareData!.external_dependencies,
            data.external_dependencies,
            (d) => d.id,
          )}
          keyOf={(d) => d.id}
          emptyLabel="None."
          renderItem={(dep) => (
            <>
              <code>{dep.id}</code> <strong>{dep.name}</strong> - {dep.purpose}
            </>
          )}
        />
      ) : data.external_dependencies.length > 0 ? (
        <ul>
          {data.external_dependencies.map((dep) => (
            <li key={dep.id}>
              <code>{dep.id}</code> <strong>{dep.name}</strong> - {dep.purpose}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}

      <h3>Azure Service Mapping</h3>
      {data.azure_mappings.length > 0 ? (
        <table className="azure-mapping-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Azure Service</th>
              <th>Category</th>
              <th>Connectivity</th>
              <th>Trust Zone</th>
              <th>Rationale</th>
            </tr>
          </thead>
          <tbody>
            {data.azure_mappings.map((mapping) => (
              <tr key={mapping.id}>
                <td>
                  <code>{mapping.component_id}</code>
                </td>
                <td>{mapping.azure_service}</td>
                <td>{mapping.service_category}</td>
                <td>{mapping.connectivity}</td>
                <td>{mapping.trust_zone}</td>
                <td>{mapping.rationale}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="muted">None.</p>
      )}

      <h3>Supporting Azure Services</h3>
      {data.supporting_azure_services.length > 0 ? (
        <ul>
          {data.supporting_azure_services.map((service) => (
            <li key={service.id}>
              <strong>{service.azure_service}</strong>{" "}
              <span className="domain-badge">{service.category}</span> - {service.purpose}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}

      <h3>Open questions</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(compareData!.open_questions, data.open_questions, (q) => q.id)}
          keyOf={(q) => q.id}
          emptyLabel="None."
          renderItem={(q) => (
            <>
              <code>{q.id}</code> {q.question}
            </>
          )}
        />
      ) : data.open_questions.length > 0 ? (
        <ul>
          {data.open_questions.map((q) => (
            <li key={q.id}>
              <code>{q.id}</code> {q.question}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}

      {!diffing && traceability.size > 0 && (
        <>
          <h3>Requirement traceability</h3>
          <ul>
            {[...traceability.entries()].map(([reqId, refs]) => (
              <li key={reqId}>
                <code>{reqId}</code> → {refs.join(", ")}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}
