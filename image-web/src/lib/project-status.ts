import type { components } from '@/api/schema'

export type ProjectStatus = components['schemas']['ProjectStatus']

/** 4 态顺序（PRD §2.3）：需求录入 → 设计中 ⇌ 客户审稿 → 已交付. */
export const PROJECT_STATUSES: ProjectStatus[] = [
  '需求录入',
  '设计中',
  '客户审稿',
  '已交付',
]

/** 合法流转表（镜像后端 domain/project_status.py，前端只做体验，后端强制）. */
export const ALLOWED_TRANSITIONS: Record<ProjectStatus, ProjectStatus[]> = {
  需求录入: ['设计中'],
  设计中: ['客户审稿'],
  客户审稿: ['设计中', '已交付'],
  已交付: [],
}

/** 流转动作的人话标签. */
export function transitionLabel(from: ProjectStatus, to: ProjectStatus): string {
  if (from === '需求录入' && to === '设计中') return '开始设计'
  if (from === '设计中' && to === '客户审稿') return '提交审稿'
  if (from === '客户审稿' && to === '设计中') return '打回改稿'
  if (from === '客户审稿' && to === '已交付') return '交付'
  return `转「${to}」`
}

/** 状态徽章配色（语义色，清晰可读）. */
export const STATUS_TONE: Record<ProjectStatus, string> = {
  需求录入: 'bg-stone-100 text-stone-600 border-stone-200',
  设计中: 'bg-teal-50 text-teal-700 border-teal-200',
  客户审稿: 'bg-amber-50 text-amber-700 border-amber-200',
  已交付: 'bg-emerald-50 text-emerald-700 border-emerald-200',
}
