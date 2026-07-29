// Static data for real Home tool destinations.

import {
  ImageIcon, LayersIcon, FlameIcon, SquarePenIcon, HistoryIcon, type LucideIcon,
} from 'lucide-react'

import { estimateCost } from './listing'

/** 工具区大 banner（直达现有工作台）。 */
export interface ToolBanner {
  key: string
  to: string
  label: string
  desc: string
  icon: LucideIcon
}

export const TOOL_BANNERS: ToolBanner[] = [
  { key: 'set', to: '/set', label: '商品套图', desc: '上传产品图，一键出整套电商图——白底 / 场景 / 卖点按需配比。',
    icon: LayersIcon },
  { key: 'clone', to: '/clone', label: '爆款图复刻', desc: '给一张想参考的爆款图，把它的风格版式套到你的产品上。',
    icon: FlameIcon },
]

/** 工具区宫格：真工具（直达）。 */
export interface ToolTile {
  key: string
  to: string
  label: string
  desc: string
  icon: LucideIcon
}

export const TOOL_TILES: ToolTile[] = [
  {
    key: 'single',
    to: '/set',
    label: '单图出图',
    desc: `只出一张 · ¥${estimateCost(1).toFixed(2)}`,
    icon: ImageIcon,
  },
  { key: 'edit', to: '/history', label: '二次编辑', desc: '从历史选一张再改', icon: SquarePenIcon },
  { key: 'history', to: '/history', label: '出图历史', desc: '回看与重新下载', icon: HistoryIcon },
]

/** 成果展示区占位案例（首发占位内容，懒加载；后续填真实案例）。 */
export interface ShowcaseItem {
  key: string
  title: string
  tag: string
}

export const SHOWCASE_PLACEHOLDERS: ShowcaseItem[] = [
  { key: 's1', title: '花生礼盒 · 整套套图', tag: '套图' },
  { key: 's2', title: '零食袋 · 爆款复刻', tag: '复刻' },
  { key: 's3', title: '坚果罐 · 场景图', tag: '场景' },
  { key: 's4', title: '糖果 · 白底主图', tag: '白底' },
  { key: 's5', title: '茶饮 · 卖点图', tag: '卖点' },
  { key: 's6', title: '干货 · 二次编辑', tag: '编辑' },
]
