/**
 * A button that opens a file picker and hands the chosen File to `onFile`.
 * Hides the native input and resets it after each pick (so re-choosing the same
 * file fires again). Style the trigger via `className`/`children`.
 */
import { useRef } from 'react'

export function FileImportButton({
  onFile,
  accept = '.yaml,.yml,.json,application/json,text/yaml,application/x-yaml',
  className,
  title,
  children,
}) {
  const ref = useRef(null)
  return (
    <>
      <button type="button" onClick={() => ref.current?.click()} title={title} className={className}>
        {children}
      </button>
      <input
        ref={ref}
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onFile(file)
          e.target.value = ''
        }}
      />
    </>
  )
}
