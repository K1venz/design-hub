export type AdminFilterValue = string | number | boolean | null | undefined
export type AdminFilters = Record<string, AdminFilterValue>

export function normalizeAdminFilters<T extends object>(
  filters: T,
): Partial<T> {
  return Object.fromEntries(
    Object.entries(filters).filter(
      ([, value]) => value !== undefined && value !== null && value !== '',
    ),
  ) as Partial<T>
}

export function adminSearchParams(filters: AdminFilters): URLSearchParams {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(normalizeAdminFilters(filters))) {
    params.set(key, String(value))
  }
  return params
}

export function adminDateRange(
  days: number,
  anchor: Date,
): { start: string; end: string } {
  const end = new Date(anchor)
  const start = new Date(anchor)
  start.setUTCDate(start.getUTCDate() - days)
  return {
    start: start.toISOString(),
    end: end.toISOString(),
  }
}
