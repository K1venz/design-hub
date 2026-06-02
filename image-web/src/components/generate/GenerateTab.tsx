import { useState } from 'react'

import { useProjectJobs } from '@/api/generation'
import { CandidateGrid } from '@/components/generate/CandidateGrid'
import { GenerateConfigForm } from '@/components/generate/GenerateConfigForm'
import { Card } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { yuan } from '@/lib/format'

export function GenerateTab({
  projectId,
  customerName,
}: {
  projectId: number
  customerName: string
}) {
  const jobs = useProjectJobs(projectId)
  const [picked, setPicked] = useState<string | null>(null)
  const activeJob = picked ?? jobs.data?.[0]?.job_id ?? null

  return (
    <div className="space-y-6">
      <Card className="space-y-4 p-6">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-foreground">出图配置</h3>
          <p className="text-xs text-muted-foreground">配置后可先成本预估，再开始出图（草稿/family_3 路由 Mock，免费）。</p>
        </div>
        <GenerateConfigForm
          projectId={projectId}
          customerName={customerName}
          onGenerated={(jobId) => setPicked(jobId)}
        />
      </Card>

      {jobs.data && jobs.data.length > 0 && (
        <Card className="space-y-4 p-6">
          <h3 className="text-sm font-semibold text-foreground">任务与选稿</h3>
          <div className="flex flex-wrap gap-2">
            {jobs.data.map((j) => {
              const on = j.job_id === activeJob
              return (
                <button
                  key={j.job_id}
                  type="button"
                  onClick={() => setPicked(j.job_id)}
                  className={cn(
                    'rounded-lg border px-3 py-2 text-left text-xs transition-colors',
                    on
                      ? 'border-primary bg-primary/5'
                      : 'border-border/70 hover:bg-accent/40',
                  )}
                >
                  <div className="font-medium text-foreground">
                    第 {j.round_no} 轮 · {j.subscene}
                  </div>
                  <div className="text-muted-foreground mt-0.5 font-mono">
                    {j.used_model} · {j.candidate_count} 张 · {yuan(j.total_cost)}
                  </div>
                </button>
              )
            })}
          </div>
          {activeJob && (
            <div className="border-border/60 border-t pt-4">
              <CandidateGrid jobId={activeJob} />
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
