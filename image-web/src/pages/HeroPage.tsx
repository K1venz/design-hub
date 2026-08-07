import { useNavigate } from 'react-router-dom'

import { IndexNavbar } from '@/components/home/IndexNavbar'
import { SiteFooter } from '@/components/layout/SiteFooter'
import { MarqueeHero } from '@/components/home/MarqueeHero'
import { useShowcase } from '@/api/showcase'

/**
 * 品牌 Hero 独立落地页（`/` index，ISSUE-0061）。用户选型拍板 MarqueeHero 版
 * （白底 + 文字栈交叠 + 底部实拍走马灯），替换初版彩带光轨。单屏、CTA → /home。
 */
export function HeroPage() {
  const navigate = useNavigate()
  const showcase = useShowcase(true)
  const images = showcase.data?.map((item) => item.url) ?? []
  return (
    <div className="relative">
      <IndexNavbar />
      <MarqueeHero
        tagline="已服务内测商家，出图超 1000 张"
        titleLines={['一整套电商图', '一句话的事']}
        description="上传产品图，白底、场景、卖点一次出齐，还能复刻爆款、文字保真。实朴帮你把商品图做到能开卖。"
        ctaText="开始创作"
        onCta={() => navigate('/home')}
        images={images}
      />
      <SiteFooter className="bg-white px-8 pb-16 pt-20 md:px-16" />
    </div>
  )
}
