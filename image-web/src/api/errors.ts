/**
 * 后端错误体：自定义边界映射为 `{ error, detail: string }`；
 * FastAPI 校验错(422) 为 `{ detail: [{ msg, loc }] }`。统一归一为一句中文。
 */
interface ApiErrorBody {
  error?: string
  detail?: unknown
}

export function errorMessage(err: unknown, fallback = '请求失败，请稍后重试'): string {
  if (!err) return fallback
  if (typeof err === 'string') return err
  if (err instanceof Error) return err.message || fallback

  const body = err as ApiErrorBody
  const detail = body.detail
  if (typeof detail === 'string' && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((item) =>
        item && typeof item === 'object' && 'msg' in item
          ? String((item as { msg: unknown }).msg)
          : '',
      )
      .filter(Boolean)
    if (msgs.length) return msgs.join('；')
  }
  if (typeof body.error === 'string' && body.error.trim()) return body.error
  return fallback
}
