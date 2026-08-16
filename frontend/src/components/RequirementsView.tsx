import { diffByKey, diffStringList } from "../lib/diff"
import type { RequirementsArtifact } from "../types"
import { DiffList } from "./DiffList"

interface RequirementsViewProps {
  data: RequirementsArtifact
  /** A second version to diff against. When set, every section renders
   * added/removed/changed instead of a flat list. */
  compareData?: RequirementsArtifact | null
}

function ScalarField({
  label,
  before,
  after,
}: {
  label: string
  before?: string
  after: string
}) {
  const changed = before !== undefined && before !== after
  return (
    <p>
      <strong>{label}:</strong>{" "}
      {changed ? (
        <>
          <span className="diff-before-inline">{before}</span>
          {" → "}
          <span className="diff-after-inline">{after}</span>
        </>
      ) : (
        after
      )}
    </p>
  )
}

export function RequirementsView({ data, compareData }: RequirementsViewProps) {
  const diffing = Boolean(compareData)

  return (
    <div className="requirements-view">
      <ScalarField label="Summary" before={compareData?.summary} after={data.summary} />
      <ScalarField
        label="Business goal"
        before={compareData?.business_goal}
        after={data.business_goal}
      />

      <h3>Actors</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(compareData!.actors, data.actors, (a) => a.name)}
          keyOf={(a) => a.name}
          emptyLabel="No actors."
          renderItem={(actor) => (
            <>
              <strong>{actor.name}</strong> — {actor.description}
            </>
          )}
        />
      ) : (
        <ul>
          {data.actors.map((actor) => (
            <li key={actor.name}>
              <strong>{actor.name}</strong> — {actor.description}
            </li>
          ))}
        </ul>
      )}

      <h3>Functional requirements</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(
            compareData!.functional_requirements,
            data.functional_requirements,
            (r) => r.id,
          )}
          keyOf={(r) => r.id}
          emptyLabel="None."
          renderItem={(req) => (
            <>
              <code>{req.id}</code> <strong>[{req.priority}]</strong> {req.description}
            </>
          )}
        />
      ) : (
        <ul>
          {data.functional_requirements.map((req) => (
            <li key={req.id}>
              <code>{req.id}</code> <strong>[{req.priority}]</strong> {req.description}
            </li>
          ))}
        </ul>
      )}

      <h3>Non-functional requirements</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(
            compareData!.non_functional_requirements,
            data.non_functional_requirements,
            (r) => r.id,
          )}
          keyOf={(r) => r.id}
          emptyLabel="None."
          renderItem={(req) => (
            <>
              <code>{req.id}</code> <strong>[{req.priority}]</strong> {req.description}
            </>
          )}
        />
      ) : (
        <ul>
          {data.non_functional_requirements.map((req) => (
            <li key={req.id}>
              <code>{req.id}</code> <strong>[{req.priority}]</strong> {req.description}
            </li>
          ))}
        </ul>
      )}

      <h3>Data requirements</h3>
      {diffing ? (
        <DiffList
          diff={diffStringList(compareData!.data_requirements, data.data_requirements)}
          keyOf={(item) => item}
          emptyLabel="None."
          renderItem={(item) => item}
        />
      ) : (
        <ul>
          {data.data_requirements.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}

      <h3>Integration requirements</h3>
      {diffing ? (
        <DiffList
          diff={diffStringList(
            compareData!.integration_requirements,
            data.integration_requirements,
          )}
          keyOf={(item) => item}
          emptyLabel="None."
          renderItem={(item) => item}
        />
      ) : (
        <ul>
          {data.integration_requirements.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}

      <h3>Constraints</h3>
      {diffing ? (
        <DiffList
          diff={diffStringList(compareData!.constraints, data.constraints)}
          keyOf={(item) => item}
          emptyLabel="None."
          renderItem={(item) => item}
        />
      ) : (
        <ul>
          {data.constraints.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}

      <h3>Assumptions</h3>
      {diffing ? (
        <DiffList
          diff={diffByKey(compareData!.assumptions, data.assumptions, (a) => a.id)}
          keyOf={(a) => a.id}
          emptyLabel="None."
          renderItem={(a) => (
            <>
              <code>{a.id}</code> {a.assumption}{" "}
              <span className="muted">({a.confidence} confidence)</span>
            </>
          )}
        />
      ) : (
        <ul>
          {data.assumptions.map((a) => (
            <li key={a.id}>
              <code>{a.id}</code> {a.assumption}{" "}
              <span className="muted">({a.confidence} confidence)</span>
            </li>
          ))}
        </ul>
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
              {q.blocking && <strong> (blocking)</strong>}
            </>
          )}
        />
      ) : data.open_questions.length > 0 ? (
        <ul>
          {data.open_questions.map((q) => (
            <li key={q.id}>
              <code>{q.id}</code> {q.question}
              {q.blocking && <strong> (blocking)</strong>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">None.</p>
      )}
    </div>
  )
}
