import { useMemo, useRef, useState } from "react"

interface DiagramViewerProps {
  svg: string
  /** Called with a component id when the user clicks a node whose Graphviz
   * `<title>` matches one, or `null` when they click empty space. Lets the
   * architecture list below highlight/scroll to match - see
   * ArchitectureView's `highlightedComponentId`. */
  onInspect?: (componentId: string | null) => void
  /** Renders a "Download PNG" button at the right edge of the toolbar
   * (grouped with Zoom in/out/Reset, since it's another way of "getting
   * this diagram out of the viewer" rather than a diagram-selection
   * control) when provided. Omitted entirely - not just disabled - when
   * there's nothing to download yet. */
  onDownloadPng?: () => void
}

const MIN_SCALE = 0.25
const MAX_SCALE = 4

/** Strip anything that could execute script from Graphviz-generated SVG
 * before injecting it. Graphviz escapes label text itself, so this is
 * defense-in-depth rather than the primary safeguard - labels can contain
 * AI-generated, ultimately user-influenced text (component names/
 * responsibilities), so treat the markup as untrusted even though it's
 * produced by our own backend. */
function sanitizeSvg(markup: string): string {
  return markup
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/\son\w+="[^"]*"/gi, "")
    .replace(/\son\w+='[^']*'/gi, "")
}

export function DiagramViewer({ svg, onInspect, onDownloadPng }: DiagramViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  const [translate, setTranslate] = useState({ x: 0, y: 0 })
  const dragState = useRef<{ startX: number; startY: number; origin: { x: number; y: number } } | null>(
    null,
  )

  const cleanSvg = useMemo(() => sanitizeSvg(svg), [svg])

  const clampScale = (value: number) => Math.min(MAX_SCALE, Math.max(MIN_SCALE, value))

  const handleWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    event.preventDefault()
    const delta = event.deltaY > 0 ? -0.1 : 0.1
    setScale((current) => clampScale(current + delta))
  }

  const handleMouseDown = (event: React.MouseEvent<HTMLDivElement>) => {
    dragState.current = {
      startX: event.clientX,
      startY: event.clientY,
      origin: translate,
    }
  }

  const handleMouseMove = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!dragState.current) return
    const dx = event.clientX - dragState.current.startX
    const dy = event.clientY - dragState.current.startY
    setTranslate({ x: dragState.current.origin.x + dx, y: dragState.current.origin.y + dy })
  }

  const stopDrag = () => {
    dragState.current = null
  }

  const handleClick = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!onInspect) return
    const target = event.target as Element
    const node = target.closest(".node")
    if (!node) {
      onInspect(null)
      return
    }
    const title = node.querySelector("title")
    onInspect(title?.textContent ?? null)
  }

  const reset = () => {
    setScale(1)
    setTranslate({ x: 0, y: 0 })
  }

  return (
    <div className="diagram-viewer">
      <div className="diagram-toolbar">
        <button type="button" onClick={() => setScale((s) => clampScale(s + 0.2))}>
          Zoom in
        </button>
        <button type="button" onClick={() => setScale((s) => clampScale(s - 0.2))}>
          Zoom out
        </button>
        <button type="button" onClick={reset}>
          Reset
        </button>
        <span className="muted">{Math.round(scale * 100)}%</span>
        {onDownloadPng && (
          <button type="button" className="diagram-download-button" onClick={onDownloadPng}>
            Download PNG
          </button>
        )}
      </div>
      <div
        ref={containerRef}
        className="diagram-canvas"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={stopDrag}
        onMouseLeave={stopDrag}
        onClick={handleClick}
      >
        <div
          className="diagram-transform"
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
          }}
          // eslint-disable-next-line react/no-danger -- see sanitizeSvg above;
          // this is our own backend's Graphviz output, not arbitrary user HTML.
          dangerouslySetInnerHTML={{ __html: cleanSvg }}
        />
      </div>
      <p className="muted diagram-hint">
        Scroll to zoom, drag to pan, click a component to inspect it.
      </p>
    </div>
  )
}
