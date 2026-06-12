import {
  LayoutPanelLeftIcon,
  HistoryIcon,
  UsersRoundIcon,
  SlidersHorizontalIcon,
  type LucideIcon,
} from 'lucide-react'

import type { Role } from '@/stores/auth-store'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** 仅管理者可见. */
  managerOnly?: boolean
  end?: boolean
}

/** 主导航（toC：工作台/历史 + 管理者后台项）。managerOnly 项对普通用户隐藏. */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '工作台', icon: LayoutPanelLeftIcon, end: true },
  { to: '/history', label: '历史', icon: HistoryIcon },
  { to: '/admin/models', label: '模型配置', icon: SlidersHorizontalIcon, managerOnly: true },
  { to: '/admin/users', label: '用户管理', icon: UsersRoundIcon, managerOnly: true },
]

export function navItemsFor(role: Role): NavItem[] {
  return NAV_ITEMS.filter((i) => !i.managerOnly || role === '管理者')
}
