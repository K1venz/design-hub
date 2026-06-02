import { Link, useParams } from 'react-router-dom'
import { ArrowLeftIcon, ImageIcon, PencilRulerIcon, PackageIcon } from 'lucide-react'

import { useCustomer } from '@/api/customers'
import { useProject } from '@/api/projects'
import { PagePlaceholder } from '@/components/PagePlaceholder'
import { BriefTab } from '@/components/project/BriefTab'
import { ProjectStatusControl } from '@/components/project/ProjectStatusControl'
import { StatusBadge } from '@/components/project/StatusBadge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PROJECT_STATUSES, type ProjectStatus } from '@/lib/project-status'

function StatusFlow({ current }: { current: ProjectStatus }) {
  const currentIdx = PROJECT_STATUSES.indexOf(current)
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs">
      {PROJECT_STATUSES.map((s, i) => {
        const active = s === current
        const passed = currentIdx > i
        return (
          <span key={s} className="flex items-center gap-1.5">
            {i > 0 && <span className="text-muted-foreground/40">→</span>}
            <span
              className={
                active
                  ? 'text-primary font-medium'
                  : passed
                    ? 'text-muted-foreground'
                    : 'text-muted-foreground/50'
              }
            >
              {s}
            </span>
          </span>
        )
      })}
    </div>
  )
}

export function ProjectDetailPage() {
  const { id } = useParams()
  const pid = id ? Number(id) : NaN
  const valid = Number.isInteger(pid)
  const project = useProject(valid ? pid : undefined)
  const customer = useCustomer(project.data?.customer_id)

  return (
    <div className="space-y-6">
      <Link
        to="/"
        className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1.5 text-sm transition-colors"
      >
        <ArrowLeftIcon className="size-4" />
        返回工作台
      </Link>

      {!valid || project.isError ? (
        <Card className="p-10 text-center">
          <p className="text-sm text-muted-foreground">项目不存在或无法访问。</p>
        </Card>
      ) : project.isLoading || !project.data ? (
        <Card className="space-y-4 p-6">
          <Skeleton className="h-7 w-64" />
          <Skeleton className="h-5 w-40" />
        </Card>
      ) : (
        <>
          <Card className="space-y-5 p-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div className="space-y-2">
                <div className="flex items-center gap-3">
                  <h2 className="text-xl font-semibold tracking-tight text-foreground">
                    {project.data.name}
                  </h2>
                  <StatusBadge status={project.data.status} />
                </div>
                <p className="text-sm text-muted-foreground">
                  {customer.data?.name ?? `客户 #${project.data.customer_id}`}
                  <span className="text-muted-foreground/50"> · </span>
                  <span className="tabular font-mono">第 {project.data.current_round} 轮</span>
                </p>
              </div>
            </div>
            <div className="border-border/70 flex flex-wrap items-center justify-between gap-4 border-t pt-5">
              <StatusFlow current={project.data.status} />
              <ProjectStatusControl project={project.data} />
            </div>
          </Card>

          <Tabs defaultValue="brief">
            <TabsList>
              <TabsTrigger value="brief">需求单</TabsTrigger>
              <TabsTrigger value="generate">出图与选稿</TabsTrigger>
              <TabsTrigger value="revision">改稿</TabsTrigger>
              <TabsTrigger value="export">交付导出</TabsTrigger>
            </TabsList>
            <TabsContent value="brief" className="pt-5">
              <BriefTab projectId={project.data.id} />
            </TabsContent>
            <TabsContent value="generate" className="pt-5">
              <PagePlaceholder
                icon={ImageIcon}
                title="出图配置 · 成本预估 · SSE · 选稿"
                description="出图配置（family/品类/子场景/档位/尺寸/风格）+ 成本预估 → 发起出图 → SSE 实时进度 → 候选图栅格 → 评分(1-5)/保留 → 可用率。"
                endpoints={['/generate/cost-preview', '/projects/{id}/generate', 'SSE /generate/{job_id}/events', '/jobs/{id}/images']}
                pkg="FE-3"
              />
            </TabsContent>
            <TabsContent value="revision" className="pt-5">
              <PagePlaceholder
                icon={PencilRulerIcon}
                title="改稿单"
                description="逐条改稿、勾选完成；交付强校验（未完成条目阻断交付，管理者可强制）。"
                endpoints={['/projects/{id}/revisions', '/revisions/{rid}/items']}
                pkg="FE-4"
              />
            </TabsContent>
            <TabsContent value="export" className="pt-5">
              <PagePlaceholder
                icon={PackageIcon}
                title="交付 / 导出归档"
                description="多格式导出（JPG/PNG/PDF）、批量改尺寸、zip、命名规范与按轮次归档。"
                endpoints={['/projects/{id}/export', '/images/{id}/resize']}
                pkg="FE-5"
              />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  )
}
