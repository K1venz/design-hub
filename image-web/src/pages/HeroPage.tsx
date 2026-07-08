import { useNavigate } from 'react-router-dom'

import { HeroLanding } from '@/components/home/HeroLanding'

/**
 * 品牌 Hero 独立落地页（`/` index，ISSUE-0061）。全屏沉浸、不套 AppShell。
 * 左下主 CTA / 顶部公告条 → 项目首页（/home）；右下副 CTA → 生成案例页。
 */
export function HeroPage() {
  const navigate = useNavigate()
  return (
    <div className="h-svh overflow-y-auto overflow-x-hidden bg-background">
      <HeroLanding onPrimary={() => navigate('/home')} onSecondary={() => navigate('/home')} />
    </div>
  )
}
