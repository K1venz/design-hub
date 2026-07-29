export function uploadPreviewUrl(url: string, token: string | null): string {
  if (!url.startsWith('/uploads/')) return url
  return `/api${url}${token ? `?access_token=${encodeURIComponent(token)}` : ''}`
}

export function uploadIdPreviewUrl(
  uploadId: string,
  token: string | null,
): string {
  return uploadPreviewUrl(`/uploads/${uploadId}`, token)
}
