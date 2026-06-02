import { ChartNoAxesCombinedIcon } from 'lucide-react'

import { PagePlaceholder } from '@/components/PagePlaceholder'

export function DashboardPage() {
  return (
    <PagePlaceholder
      icon={ChartNoAxesCombinedIcon}
      title="业务仪表盘"
      description="成本 5 维报表（总览 / 模型 / 项目 / 设计师 / 档位 × 月 / 周 / 日），recharts 可视化。仅管理者可见。"
      endpoints={['/dashboard/cost?dim=&period=']}
      pkg="FE-6"
    />
  )
}
