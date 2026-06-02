import {
  LayoutPanelLeftIcon,
  UsersIcon,
  UsersRoundIcon,
  ChartNoAxesCombinedIcon,
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

/** 主导航。FE-1~7 在此登记各业务页；managerOnly 项对设计师隐藏. */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: '工作台', icon: LayoutPanelLeftIcon, end: true },
  { to: '/customers', label: '客户', icon: UsersIcon },
  { to: '/dashboard', label: '业务仪表盘', icon: ChartNoAxesCombinedIcon, managerOnly: true },
  { to: '/admin/models', label: '模型配置', icon: SlidersHorizontalIcon, managerOnly: true },
  { to: '/admin/users', label: '用户管理', icon: UsersRoundIcon, managerOnly: true },
]

export function navItemsFor(role: Role): NavItem[] {
  return NAV_ITEMS.filter((i) => !i.managerOnly || role === '管理者')
}
