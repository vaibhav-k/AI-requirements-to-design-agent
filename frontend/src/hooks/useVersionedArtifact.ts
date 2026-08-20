import { useEffect, useState } from "react"

import { describeError } from "../api"

interface UseVersionedArtifactArgs<T> {
  sessionId: string
  /** Bumped by the caller whenever a new version may have been persisted
   * (e.g. after a refine/accept completes), to force a re-fetch of the
   * version list without this hook needing to know why. */
  refreshKey: number
  listVersions: (sessionId: string) => Promise<number[]>
  getVersion: (sessionId: string, version: number) => Promise<T>
}

interface UseVersionedArtifactResult<T> {
  versions: number[]
  selected: number | null
  setSelected: (version: number) => void
  compareWith: number | null
  setCompareWith: (version: number | null) => void
  data: T | null
  compareData: T | null
  loading: boolean
  error: string | null
}

/** Version history + "currently viewing" + "comparing against" state for
 * one artifact type (requirements or architecture) of one session. Fetches
 * only what's actually persisted - never fabricates a version or its
 * content - via the `listVersions`/`getVersion` callbacks the caller
 * supplies (typically `api.listRequirementsVersions`/`api.getRequirementsVersion`,
 * or the architecture equivalents).
 *
 * Shared between the Requirements and Architecture panels so "pick a
 * version, optionally pick a second to compare against" isn't implemented
 * twice.
 */
export function useVersionedArtifact<T>({
  sessionId,
  refreshKey,
  listVersions,
  getVersion,
}: UseVersionedArtifactArgs<T>): UseVersionedArtifactResult<T> {
  const [versions, setVersions] = useState<number[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [compareWith, setCompareWith] = useState<number | null>(null)
  const [data, setData] = useState<T | null>(null)
  const [compareData, setCompareData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Load the version list for this session, defaulting the selection to
  // the latest version whenever the session or refreshKey changes.
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    listVersions(sessionId)
      .then((result) => {
        if (cancelled) return
        setVersions(result)
        setSelected((current) => {
          if (result.length === 0) return null
          if (current !== null && result.includes(current)) return current
          return result[result.length - 1]
        })
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(`Could not load version history: ${describeError(err)}`)
      })
    return () => {
      cancelled = true
    }
    // `listVersions` is one of useRequirementsApi's memoized methods (see
    // api.ts), so its identity is stable across renders unless the
    // underlying MSAL account changes - safe to list here without causing
    // an extra re-list loop.
  }, [sessionId, refreshKey, listVersions])

  // Load the selected version's content.
  useEffect(() => {
    if (selected === null) {
      setData(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    getVersion(sessionId, selected)
      .then((result) => {
        if (!cancelled) setData(result)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(`Could not load this version: ${describeError(err)}`)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
    // `getVersion` is stable per the same reasoning as `listVersions` above.
  }, [sessionId, selected, getVersion])

  // Load the compare-with version's content, when set.
  useEffect(() => {
    if (compareWith === null) {
      setCompareData(null)
      return
    }
    let cancelled = false
    getVersion(sessionId, compareWith)
      .then((result) => {
        if (!cancelled) setCompareData(result)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setError(`Could not load the comparison version: ${describeError(err)}`)
      })
    return () => {
      cancelled = true
    }
    // `getVersion` is stable per the same reasoning as `listVersions` above.
  }, [sessionId, compareWith, getVersion])

  return { versions, selected, setSelected, compareWith, setCompareWith, data, compareData, loading, error }
}
