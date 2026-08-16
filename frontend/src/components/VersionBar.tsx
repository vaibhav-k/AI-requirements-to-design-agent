interface VersionBarProps {
  versions: number[]
  selected: number | null
  onSelect: (version: number) => void
  compareWith: number | null
  onCompareChange: (version: number | null) => void
  latestVersion: number | null
}

export function VersionBar({
  versions,
  selected,
  onSelect,
  compareWith,
  onCompareChange,
  latestVersion,
}: VersionBarProps) {
  if (versions.length === 0) {
    return null
  }

  return (
    <div className="version-bar">
      <label>
        Version
        <select
          value={selected ?? ""}
          onChange={(event) => onSelect(Number(event.target.value))}
        >
          {versions.map((v) => (
            <option key={v} value={v}>
              v{v}
              {v === latestVersion ? " (latest)" : ""}
            </option>
          ))}
        </select>
      </label>

      {versions.length > 1 && (
        <label>
          Compare with
          <select
            value={compareWith ?? ""}
            onChange={(event) =>
              onCompareChange(event.target.value ? Number(event.target.value) : null)
            }
          >
            <option value="">None</option>
            {versions
              .filter((v) => v !== selected)
              .map((v) => (
                <option key={v} value={v}>
                  v{v}
                </option>
              ))}
          </select>
        </label>
      )}
    </div>
  )
}
