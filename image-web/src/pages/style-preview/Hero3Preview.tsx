import { MarqueeHero } from '@/components/home/MarqueeHero'

// DEV-only 预览（hero-3 复刻考验）：走马灯用本地 generated 真实出图（vite /__localimg dev 图床）。
const GEN = '/Users/Zhuanz/CLAUDE/image-gen/image-code/generated'
const IMAGES = [
  '0d92feb99fbab119',
  '1eefddf7817977db',
  '246f6ede041a4db9',
  '3098e021000cb9df',
  '38649ef18aab21f6',
  '41456dfd19a59f9c',
  '45e44b0be1d71108',
  '60c21b4106db5193',
  '646a4327d24c053c',
  '800dafd30b57c1e5',
  '829999e37d136090',
  '90b1ad78f8d61757',
].map((k) => `/__localimg?p=${encodeURIComponent(`${GEN}/${k}.png`)}`)

export function Hero3Preview() {
  return (
    <MarqueeHero
      tagline="已服务内测商家，出图超 1000 张"
      titleLines={['一整套电商图', '一句话的事']}
      description="上传产品图，白底、场景、卖点一次出齐，还能复刻爆款、文字保真。实朴帮你把商品图做到能开卖。"
      ctaText="开始创作"
      onCta={() => (window.location.href = '/home')}
      images={IMAGES}
    />
  )
}
