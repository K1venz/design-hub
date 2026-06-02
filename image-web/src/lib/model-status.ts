/**
 * 模型接通状态（前端展示层维护——后端 ModelConfig 不含此字段）。
 * 现状：gpt-image-2 已接通可用；qwen-image-pro 作备选；其余 Provider 尚未接通。
 * 接通新 Provider 后在此更新即可。
 */
export type ConnStatus = 'live' | 'standby' | 'unconnected'

const STATUS_MAP: Record<string, ConnStatus> = {
  'gpt-image-2': 'live',
  'qwen-image-pro': 'standby',
}

export function connStatus(name: string): ConnStatus {
  return STATUS_MAP[name] ?? 'unconnected'
}

export const CONN_META: Record<ConnStatus, { label: string; tone: string; order: number }> = {
  live: { label: '已接通', tone: 'border-emerald-200 bg-emerald-50 text-emerald-700', order: 0 },
  standby: { label: '备选', tone: 'border-amber-200 bg-amber-50 text-amber-700', order: 1 },
  unconnected: {
    label: '未接通',
    tone: 'border-border bg-muted text-muted-foreground',
    order: 2,
  },
}
