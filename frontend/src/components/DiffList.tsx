import type { ListDiff } from "../lib/diff"

interface DiffListProps<T> {
  diff: ListDiff<T>
  renderItem: (item: T) => React.ReactNode
  keyOf: (item: T) => string
  emptyLabel?: string
}

/** Renders a diffed list: unchanged items plain, added/removed/changed
 * items tagged and colored. Used identically for requirements lists
 * (actors, functional requirements, ...) and architecture lists
 * (components, interfaces, ...) - the diff shape is the same either way. */
export function DiffList<T>({ diff, renderItem, keyOf, emptyLabel }: DiffListProps<T>) {
  const { added, removed, changed, unchanged } = diff
  const isEmpty =
    added.length === 0 && removed.length === 0 && changed.length === 0 && unchanged.length === 0

  if (isEmpty) {
    return emptyLabel ? <p className="muted">{emptyLabel}</p> : null
  }

  return (
    <ul className="diff-list">
      {unchanged.map((item) => (
        <li key={keyOf(item)}>{renderItem(item)}</li>
      ))}
      {removed.map((item) => (
        <li key={keyOf(item)} className="diff-removed">
          <span className="diff-tag">removed</span>
          {renderItem(item)}
        </li>
      ))}
      {added.map((item) => (
        <li key={keyOf(item)} className="diff-added">
          <span className="diff-tag">added</span>
          {renderItem(item)}
        </li>
      ))}
      {changed.map(({ before, after }) => (
        <li key={keyOf(after)} className="diff-changed">
          <span className="diff-tag">changed</span>
          <div className="diff-before">{renderItem(before)}</div>
          <div className="diff-after">{renderItem(after)}</div>
        </li>
      ))}
    </ul>
  )
}
