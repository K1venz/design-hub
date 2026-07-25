// Canned fixture data for the throwaway style previews (/style-preview/*).
// Same representative content across all four styles so only the design
// language differs. DEV-gated routes — never reaches the prod bundle.
//
// Assets are gitignored (public/preview/, ~12MB). To re-render locally,
// copy from the repo's QA evidence (run at repo root):
//   mkdir -p image-web/public/preview
//   cp "image-qa/套图回归/花生-白底.png"        image-web/public/preview/wb-white.png
//   cp "image-qa/套图回归/花生-场景.png"        image-web/public/preview/wb-scene1.png
//   cp "image-qa/路A实测/路A-花生-散落紫米.png" image-web/public/preview/wb-scene2.png
//   cp "image-qa/套图回归/花生-卖点-有字.png"   image-web/public/preview/wb-sell1.png
//   cp "image-qa/通用块多产品/通用块-花生.png"  image-web/public/preview/wb-sell2.png
//   cp image-code/.playwright-mcp/3d579b6bd423ce51.png image-web/public/preview/wb-upload.png

import { estimateCost } from '../../lib/listing'

export interface PreviewImage {
  src: string
  type: '白底' | '场景' | '卖点'
  no: string
  cost: string
}

const PREVIEW_UNIT_COST = `¥${estimateCost(1).toFixed(2)}`

export const PREVIEW_RESULTS: PreviewImage[] = [
  { src: '/preview/wb-white.png', type: '白底', no: '01', cost: PREVIEW_UNIT_COST },
  { src: '/preview/wb-scene1.png', type: '场景', no: '02', cost: PREVIEW_UNIT_COST },
  { src: '/preview/wb-scene2.png', type: '场景', no: '03', cost: PREVIEW_UNIT_COST },
  { src: '/preview/wb-sell1.png', type: '卖点', no: '04', cost: PREVIEW_UNIT_COST },
  { src: '/preview/wb-sell2.png', type: '卖点', no: '05', cost: PREVIEW_UNIT_COST },
]

export const PREVIEW_UPLOAD = '/preview/wb-upload.png'

export const PREVIEW_GROUPS = [
  { key: '白底', label: '白底图', latin: 'WHITE BG', count: 1 },
  { key: '场景', label: '场景图', latin: 'SCENE', count: 2 },
  { key: '卖点', label: '卖点图', latin: 'FEATURE', count: 2 },
] as const

export const PREVIEW_PROMPT = '高山七彩花生，颗颗饱满，礼盒装；早餐桌木质感，自然晨光'
export const PREVIEW_OVERLAYS = ['高山七彩花生', '现摘现炒']

export const PREVIEW_PLAN = [
  { label: '白底图', desc: '白底主图，呈现商品细节', n: 1 },
  { label: '场景图', desc: '生活使用场景展示', n: 2 },
  { label: '卖点图', desc: '核心卖点与细节特写', n: 2 },
]

export const PREVIEW_MODIFIERS = [
  { label: '电商平台', value: '淘宝天猫1688' },
  { label: '语言', value: '中文' },
  { label: '比例', value: '1:1' },
]
