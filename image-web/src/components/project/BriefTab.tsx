import { useBrief } from '@/api/brief'
import { AssetPanel } from '@/components/project/AssetPanel'
import { BriefForm } from '@/components/project/BriefForm'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'

export function BriefTab({ projectId }: { projectId: number }) {
  const brief = useBrief(projectId)
  return (
    <div className="space-y-5">
      {brief.isLoading ? (
        <Card className="space-y-4 p-6">
          <Skeleton className="h-9 w-full" />
          <Skeleton className="h-9 w-2/3" />
          <Skeleton className="h-20 w-full" />
        </Card>
      ) : (
        <BriefForm projectId={projectId} initial={brief.data ?? null} />
      )}
      <AssetPanel projectId={projectId} />
    </div>
  )
}
