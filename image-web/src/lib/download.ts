/**
 * Force-download an image. Tries fetch→blob (real download, works same-origin / CORS-enabled);
 * falls back to opening in a new tab when the fetch is blocked (e.g. cross-origin without CORS).
 */
export async function downloadImage(url: string, filename: string): Promise<void> {
  try {
    const res = await fetch(url)
    if (!res.ok) throw new Error(String(res.status))
    const blob = await res.blob()
    const objectUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objectUrl
    a.download = filename
    a.click()
    URL.revokeObjectURL(objectUrl)
  } catch {
    window.open(url, '_blank', 'noopener')
  }
}
