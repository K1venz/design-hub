/** "1.1900" → "¥1.19"（金额字符串规整为两位小数）. */
export function yuan(v: string | number): string {
  const n = typeof v === 'number' ? v : Number(v)
  return `¥${Number.isFinite(n) ? n.toFixed(2) : '0.00'}`
}

/** 0.732 → "73%"（占比小数转百分比）. */
export function percent(v: number, digits = 0): string {
  return `${(v * 100).toFixed(digits)}%`
}
