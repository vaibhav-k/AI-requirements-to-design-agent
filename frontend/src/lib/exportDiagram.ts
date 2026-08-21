/** Rasterize an architecture diagram's SVG markup to a PNG and trigger a
 * browser download - entirely client-side, no backend round trip.
 *
 * This works without tainting the canvas (which would otherwise block
 * `toBlob`/`toDataURL`) only because the SVG the backend renders has
 * every icon already inlined as a base64 `data:` URI - see
 * `ArchitectureDiagramGenerator._inline_local_images` in
 * `backend/tools-service/src/infrastructure/diagram.py`. An SVG that
 * still referenced external images would mark the canvas
 * "origin-unclean" and every export below would silently produce a
 * blank/broken download instead.
 */
export function downloadSvgAsPng(
  svg: string,
  filename: string,
  options: { scale?: number; onError?: (message: string) => void } = {},
): void {
  const { scale = 2, onError } = options
  const image = new Image()
  const svgBlob = new Blob([svg], { type: "image/svg+xml;charset=utf-8" })
  const svgUrl = URL.createObjectURL(svgBlob)

  image.onload = () => {
    // Graphviz's SVG always declares real pixel dimensions (`width`/
    // `height` attributes derived from the rendered layout), so the
    // loaded `<img>` reports its natural size correctly - no need to
    // parse the SVG's `viewBox` ourselves.
    const width = image.naturalWidth || 1600
    const height = image.naturalHeight || 1200

    const canvas = document.createElement("canvas")
    canvas.width = width * scale
    canvas.height = height * scale

    const context = canvas.getContext("2d")
    if (!context) {
      URL.revokeObjectURL(svgUrl)
      onError?.("Could not create a canvas to render the PNG.")
      return
    }

    // The diagram itself is drawn on a white background already
    // (`_create_graph`'s `bgcolor="white"`), but filling explicitly
    // here guards against any transparent margin reading as black
    // once flattened to PNG (PNG has no notion of "page background").
    context.fillStyle = "white"
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(image, 0, 0, canvas.width, canvas.height)

    canvas.toBlob((blob) => {
      URL.revokeObjectURL(svgUrl)
      if (!blob) {
        onError?.("Could not encode the diagram as a PNG.")
        return
      }

      const downloadUrl = URL.createObjectURL(blob)
      const link = document.createElement("a")
      link.href = downloadUrl
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      URL.revokeObjectURL(downloadUrl)
    }, "image/png")
  }

  image.onerror = () => {
    URL.revokeObjectURL(svgUrl)
    onError?.("Could not load the diagram SVG for PNG conversion.")
  }

  image.src = svgUrl
}
