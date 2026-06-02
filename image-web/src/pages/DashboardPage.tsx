import { useState } from 'react'
import { CoinsIcon, ImagesIcon, ReceiptTextIcon, TrendingUpIcon } from 'lucide-react'

import {
  useDesignerCosts,
  useModelCosts,
  useOverview,
  useProjectCosts,
  useTierCosts,
  type Period,
} from '@/api/dashboard'
import { CostBarChart, TierShareChart } from '@/components/dashboard/CostCharts'
import { KpiCard } from '@/components/dashboard/KpiCard'
import { Card } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { percent, yuan } from '@/lib/format'

const PERIOD_LABEL: Record<Period, string> = { month: '本月', week: '本周', day: '今日' }

export function DashboardPage() {
  const [period, setPeriod] = useState<Period>('month')
  const overview = useOverview(period)
  const models = useModelCosts(period)
  const tiers = useTierCosts(period)
  const designers = useDesignerCosts(period)
  const projects = useProjectCosts(period)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight text-foreground">业务仪表盘</h2>
          <p className="text-sm text-muted-foreground">成本与产能 5 维报表（{PERIOD_LABEL[period]}）。仅管理者可见。</p>
        </div>
        <Select value={period} onValueChange={(v) => setPeriod(v as Period)}>
          <SelectTrigger className="w-32" size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="month">本月</SelectItem>
            <SelectItem value="week">本周</SelectItem>
            <SelectItem value="day">今日</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          icon={ImagesIcon}
          label="总出图数"
          loading={overview.isLoading}
          value={overview.data ? String(overview.data.total_images) : '—'}
        />
        <KpiCard
          icon={CoinsIcon}
          label="总成本"
          loading={overview.isLoading}
          value={overview.data ? yuan(overview.data.total_cost) : '—'}
        />
        <KpiCard
          icon={ReceiptTextIcon}
          label="单张均价"
          loading={overview.isLoading}
          value={overview.data ? yuan(overview.data.avg_cost) : '—'}
        />
        <KpiCard
          icon={TrendingUpIcon}
          label="可用率"
          hint="评分 ≥4 星占比"
          loading={overview.isLoading}
          value={overview.data ? percent(overview.data.usable_rate) : '—'}
        />
      </div>

      <Tabs defaultValue="model">
        <TabsList>
          <TabsTrigger value="model">模型成本</TabsTrigger>
          <TabsTrigger value="tier">档位结构</TabsTrigger>
          <TabsTrigger value="designer">设计师</TabsTrigger>
          <TabsTrigger value="project">项目</TabsTrigger>
        </TabsList>

        <TabsContent value="model" className="pt-5">
          <Card className="p-5">
            <CostBarChart
              rows={(models.data ?? []).map((m) => ({ label: m.model, value: Number(m.cost) }))}
            />
          </Card>
        </TabsContent>
        <TabsContent value="tier" className="pt-5">
          <Card className="p-5">
            <TierShareChart
              rows={(tiers.data ?? []).map((t) => ({
                tier: t.tier,
                actual: t.actual_share,
                target: t.target_share,
              }))}
            />
          </Card>
        </TabsContent>
        <TabsContent value="designer" className="pt-5">
          <Card className="p-5">
            <CostBarChart
              rows={(designers.data ?? []).map((d) => ({ label: d.user_id, value: Number(d.cost) }))}
            />
          </Card>
        </TabsContent>
        <TabsContent value="project" className="pt-5">
          <Card className="p-5">
            <CostBarChart
              rows={(projects.data ?? []).map((p) => ({
                label: p.project_id == null ? '未挂项目' : `#${p.project_id}`,
                value: Number(p.cost),
              }))}
            />
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  )
}
