import {
  FlameIcon,
  HistoryIcon,
  HomeIcon,
  LayersIcon,
  SlidersHorizontalIcon,
  UsersRoundIcon,
  WandSparklesIcon,
  type LucideIcon,
} from 'lucide-react'

import { ROLE_MANAGER, type Role } from '@/stores/auth-store'

export interface NavigationItem {
  to: string
  label: string
  icon: LucideIcon
  end?: boolean
}

export const PRIMARY_NAV_ITEMS: readonly NavigationItem[] = [
  { to: '/home', label: '首页', icon: HomeIcon, end: true },
  { to: '/chat', label: '帮我设计', icon: WandSparklesIcon },
  { to: '/set', label: '商品套图', icon: LayersIcon },
  { to: '/clone', label: '爆款复刻', icon: FlameIcon },
  { to: '/history', label: '历史', icon: HistoryIcon },
]

const MANAGER_NAV_ITEMS: readonly NavigationItem[] = [
  { to: '/admin/models', label: '模型配置', icon: SlidersHorizontalIcon },
  { to: '/admin/users', label: '用户管理', icon: UsersRoundIcon },
]

export function getAccountNavItems(role: Role): readonly NavigationItem[] {
  return role === ROLE_MANAGER ? MANAGER_NAV_ITEMS : []
}
