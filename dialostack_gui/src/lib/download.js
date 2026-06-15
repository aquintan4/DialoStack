/**
 * Browser file-download helpers: trigger a text download and build timestamps
 * for generated file names.
 */

/** Downloads a text as a file in the browser. */
export function downloadFile(name, text, mime) {
  const blob = new Blob([text], { type: mime })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = name
  a.click()
  URL.revokeObjectURL(a.href)
}

/** Timestamp for file names: YYYYMMDD-HHMM(SS). */
export function fileStamp(date = new Date(), withSeconds = true) {
  const p = (n) => String(n).padStart(2, '0')
  const base = `${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}`
    + `-${p(date.getHours())}${p(date.getMinutes())}`
  return withSeconds ? `${base}${p(date.getSeconds())}` : base
}
