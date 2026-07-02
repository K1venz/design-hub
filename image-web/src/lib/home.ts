// 新公开首页内容数据（spec 2026-07-02 §三）。纯静态、无 IO；页面组件消费。
// 快捷卡=实朴真实创作预设，点卡→预填对话意图带进 /chat（未登录先登录）。

import {
  ImageIcon, SparklesIcon, TagIcon, LayersIcon, FlameIcon, SquarePenIcon,
  HistoryIcon, EraserIcon, ExpandIcon, type LucideIcon,
} from 'lucide-react'

/** Hero 6 张快捷卡：实朴真实能力，点卡预填一句对话意图进「帮我设计」。 */
export interface QuickCard {
  key: string
  label: string
  desc: string
  icon: LucideIcon
  /** 预填进对话的首句意图（带进 /chat）。 */
  intent: string
}

export const QUICK_CARDS: QuickCard[] = [
  { key: 'white', label: '白底主图', desc: '纯白底 · 平台合规主图', icon: ImageIcon,
    intent: '帮我的产品出一张白底主图，产品居中、细节清晰。' },
  { key: 'scene', label: '场景图', desc: '生活使用场景 · 有氛围', icon: SparklesIcon,
    intent: '帮我的产品出一张生活使用场景图，自然光、有氛围。' },
  { key: 'sell', label: '卖点图', desc: '核心卖点 · 细节特写', icon: TagIcon,
    intent: '帮我的产品出一张卖点图，突出核心卖点和细节特写。' },
  { key: 'set', label: '整套套图', desc: '白底+场景+卖点 一键成套', icon: LayersIcon,
    intent: '给我的产品出一整套电商图，白底、场景、卖点都要。' },
  { key: 'clone', label: '爆款复刻', desc: '照着爆款图出你的', icon: FlameIcon,
    intent: '我有一张想参考的爆款图，帮我照它的风格出我的产品图。' },
  { key: 'edit', label: '二次编辑', desc: '对已出的图再调整', icon: SquarePenIcon,
    intent: '我想对之前出好的一张图再改一下。' },
]

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
  { key: 'single', to: '/set', label: '单图出图', desc: '只出一张 · ¥0.40', icon: ImageIcon },
  { key: 'edit', to: '/history', label: '二次编辑', desc: '从历史选一张再改', icon: SquarePenIcon },
  { key: 'history', to: '/history', label: '出图历史', desc: '回看与重新下载', icon: HistoryIcon },
]

/** 「即将上线」预告卡（≤2，取自美图迁移调研第一波；不可点、明确标注）。 */
export interface ComingSoonTile {
  key: string
  label: string
  desc: string
  icon: LucideIcon
}

export const COMING_SOON: ComingSoonTile[] = [
  { key: 'erase', label: 'AI 消除', desc: '一键擦除画面里的多余物件', icon: EraserIcon },
  { key: 'expand', label: '智能扩图', desc: '自动补全画面、改比例不裁切', icon: ExpandIcon },
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
