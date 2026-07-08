import { useNavigate } from 'react-router-dom'

import { IndexNavbar } from '@/components/home/IndexNavbar'
import { MarqueeHero } from '@/components/home/MarqueeHero'
import img01 from '@/assets/hero/0d92feb99fbab119.jpg'
import img02 from '@/assets/hero/1eefddf7817977db.jpg'
import img03 from '@/assets/hero/246f6ede041a4db9.jpg'
import img04 from '@/assets/hero/3098e021000cb9df.jpg'
import img05 from '@/assets/hero/38649ef18aab21f6.jpg'
import img06 from '@/assets/hero/41456dfd19a59f9c.jpg'
import img07 from '@/assets/hero/45e44b0be1d71108.jpg'
import img08 from '@/assets/hero/60c21b4106db5193.jpg'
import img09 from '@/assets/hero/646a4327d24c053c.jpg'
import img10 from '@/assets/hero/800dafd30b57c1e5.jpg'
import img11 from '@/assets/hero/829999e37d136090.jpg'
import img12 from '@/assets/hero/90b1ad78f8d61757.jpg'

// 走马灯 = 实朴真实出图（512px jpeg 打包静态资源：首屏零 API 依赖、prod 可用）。
const IMAGES = [img01, img02, img03, img04, img05, img06, img07, img08, img09, img10, img11, img12]

/**
 * 品牌 Hero 独立落地页（`/` index，ISSUE-0061）。用户选型拍板 MarqueeHero 版
 * （白底 + 文字栈交叠 + 底部实拍走马灯），替换初版彩带光轨。单屏、CTA → /home。
 */
export function HeroPage() {
  const navigate = useNavigate()
  return (
    <div className="relative">
      <IndexNavbar />
      <MarqueeHero
        tagline="已服务内测商家，出图超 1000 张"
        titleLines={['一整套电商图', '一句话的事']}
        description="上传产品图，白底、场景、卖点一次出齐，还能复刻爆款、文字保真。实朴帮你把商品图做到能开卖。"
        ctaText="开始创作"
        onCta={() => navigate('/home')}
        images={IMAGES}
      />
    </div>
  )
}
