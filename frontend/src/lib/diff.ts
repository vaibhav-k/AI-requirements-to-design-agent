/** Generic, id-keyed list diff — used to compare two versions of the same
 * artifact list (functional_requirements, components, interfaces, ...)
 * without writing a bespoke comparator per field. Equality is structural
 * (JSON-stringify), which is sufficient here since every item comes from
 * the same backend Pydantic model on both sides — key order is stable
 * across versions of the same schema.
 */
export interface ListDiff<T> {
  added: T[]
  removed: T[]
  changed: Array<{ before: T; after: T }>
  unchanged: T[]
}

export function diffByKey<T>(
  before: T[],
  after: T[],
  keyOf: (item: T) => string,
): ListDiff<T> {
  const beforeMap = new Map(before.map((item) => [keyOf(item), item]))
  const afterMap = new Map(after.map((item) => [keyOf(item), item]))

  const added: T[] = []
  const changed: Array<{ before: T; after: T }> = []
  const unchanged: T[] = []

  for (const [key, afterItem] of afterMap) {
    const beforeItem = beforeMap.get(key)
    if (beforeItem === undefined) {
      added.push(afterItem)
    } else if (JSON.stringify(beforeItem) !== JSON.stringify(afterItem)) {
      changed.push({ before: beforeItem, after: afterItem })
    } else {
      unchanged.push(afterItem)
    }
  }

  const removed: T[] = []
  for (const [key, beforeItem] of beforeMap) {
    if (!afterMap.has(key)) {
      removed.push(beforeItem)
    }
  }

  return { added, removed, changed, unchanged }
}

/** Diff a list of plain strings (data_requirements, constraints, ...) —
 * these have no id, so the string itself is the key. */
export function diffStringList(before: string[], after: string[]): ListDiff<string> {
  return diffByKey(before, after, (item) => item)
}
