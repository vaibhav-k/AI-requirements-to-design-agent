import { useCallback, useEffect, useRef, useState } from "react"

interface UseResizableWidthOptions {
  /** Width (px) used the first time this panel is ever shown, or whenever
   * `localStorage` has nothing usable stored under `storageKey`. */
  defaultWidth: number
  min: number
  max: number
  /** `localStorage` key this panel's width is persisted under, so a drag
   * survives a reload - scoped per-panel (e.g. "sidebar-width" vs.
   * "workspace-conversation-width") since each is independent. */
  storageKey: string
}

function readStoredWidth(storageKey: string, min: number, max: number, fallback: number): number {
  if (typeof window === "undefined") return fallback
  const stored = window.localStorage.getItem(storageKey)
  const parsed = stored === null ? NaN : Number(stored)
  if (!Number.isFinite(parsed)) return fallback
  return Math.min(max, Math.max(min, parsed))
}

/** Drag-to-resize for a single panel's width, backed by a draggable handle
 * on its trailing edge. Returns the current width plus a `startDrag`
 * mousedown handler to attach to that handle - dragging right widens the
 * panel, dragging left narrows it, clamped to `[min, max]`.
 *
 * Deliberately plain `mousedown`/`mousemove`/`mouseup` on `window` rather
 * than a drag-and-drop library: a resize handle only needs to track the
 * cursor while the button is held, and attaching to `window` (not the
 * handle element) means the drag keeps tracking even if the cursor
 * outruns the handle mid-drag.
 */
export function useResizableWidth({
  defaultWidth,
  min,
  max,
  storageKey,
}: UseResizableWidthOptions): { width: number; startDrag: (event: React.MouseEvent) => void } {
  const [width, setWidth] = useState<number>(() =>
    readStoredWidth(storageKey, min, max, defaultWidth),
  )
  const draggingRef = useRef(false)

  useEffect(() => {
    window.localStorage.setItem(storageKey, String(width))
  }, [width, storageKey])

  const startDrag = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault()
      draggingRef.current = true
      const startX = event.clientX
      const startWidth = width
      document.body.style.cursor = "col-resize"
      document.body.style.userSelect = "none"

      const onMove = (moveEvent: MouseEvent) => {
        if (!draggingRef.current) return
        const next = startWidth + (moveEvent.clientX - startX)
        setWidth(Math.min(max, Math.max(min, next)))
      }
      const onUp = () => {
        draggingRef.current = false
        document.body.style.cursor = ""
        document.body.style.userSelect = ""
        window.removeEventListener("mousemove", onMove)
        window.removeEventListener("mouseup", onUp)
      }
      window.addEventListener("mousemove", onMove)
      window.addEventListener("mouseup", onUp)
    },
    [width, min, max],
  )

  return { width, startDrag }
}
