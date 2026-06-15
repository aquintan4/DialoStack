import { useEffect, useRef, useState } from 'react'

/**
 * State of a popover/menu: `open` + the container `ref`, which closes on a
 * click outside or pressing Escape. Encapsulates the pattern repeated in the
 * header menus (TagFilter, ExportMenu, CopyTaskMenu, Prompts bar).
 *
 * Usage:
 *   const { open, setOpen, ref } = usePopover()
 *   <div ref={ref}><button onClick={() => setOpen(o => !o)} />{open && <menu/>}</div>
 */
export function usePopover() {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return { open, setOpen, ref }
}
