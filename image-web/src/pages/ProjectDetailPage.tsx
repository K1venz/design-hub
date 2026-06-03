import { Link, useParams } from 'react-router-dom'
import { ArrowLeftIcon } from 'lucide-react'

import { useCustomer } from '@/api/customers'
import { useProject } from '@/api/projects'
import { ExportTab } from '@/components/export/ExportTab'
import { GenerateStudio } from '@/components/generate/GenerateStudio'
import { RevisionTab } from '@/components/revision/RevisionTab'
import { ProjectPipeline } from '@/components/project/ProjectPipeline'
import { ProjectStatusControl } from '@/components/project/ProjectStatusControl'
import { StatusBadge } from '@/components/project/StatusBadge'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'

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
            <div className="border-border/70 flex flex-wrap items-center justify-between gap-6 border-t pt-5">
              <ProjectPipeline current={project.data.status} />
              <ProjectStatusControl project={project.data} />
            </div>
          </Card>

          <Tabs defaultValue="studio">
            <TabsList>
              <TabsTrigger value="studio">出图工作台</TabsTrigger>
              <TabsTrigger value="revision">改稿</TabsTrigger>
              <TabsTrigger value="export">交付导出</TabsTrigger>
            </TabsList>
            <TabsContent value="studio" className="pt-5">
              <GenerateStudio
                projectId={project.data.id}
                customerName={customer.data?.name ?? `客户 #${project.data.customer_id}`}
              />
            </TabsContent>
            <TabsContent value="revision" className="pt-5">
              <RevisionTab projectId={project.data.id} />
            </TabsContent>
            <TabsContent value="export" className="pt-5">
              <ExportTab projectId={project.data.id} />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  )
}
