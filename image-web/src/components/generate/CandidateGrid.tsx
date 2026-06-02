import { BookmarkIcon, CheckIcon } from 'lucide-react'
import { toast } from 'sonner'

import { useJobImages, useKeepImage, useScoreImage, useUsableRate } from '@/api/selection'
import { ImageThumb } from '@/components/generate/ImageThumb'
import { StarRating } from '@/components/generate/StarRating'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { percent } from '@/lib/format'

export function CandidateGrid({ jobId }: { jobId: string }) {
  const images = useJobImages(jobId)
  const rate = useUsableRate(jobId)
  const score = useScoreImage(jobId)
  const keep = useKeepImage(jobId)

  async function setScore(imageId: number, n: number) {
    try {
      await score.mutateAsync({ imageId, score: n })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '评分失败')
    }
  }
  async function toggleKeep(imageId: number, kept: boolean) {
    try {
      await keep.mutateAsync({ imageId, kept: !kept })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保留操作失败')
    }
  }

  if (images.isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="aspect-square w-full" />
        ))}
      </div>
    )
  }
  if (!images.data || images.data.length === 0) {
    return <p className="py-8 text-center text-sm text-muted-foreground">该任务暂无候选图。</p>
  }

  return (
    <div className="space-y-4">
      {rate.data && (
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">可用率</span>
          <span className="tabular text-highlight-foreground font-semibold">
            {percent(rate.data.rate)}
          </span>
          <span className="text-muted-foreground/70 text-xs">
            （{rate.data.usable}/{rate.data.total} 张 ≥4 星）
          </span>
        </div>
      )}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {images.data.map((img) => {
          const usable = (img.score ?? 0) >= 4
          return (
            <div
              key={img.id}
              className={cn(
                'overflow-hidden rounded-lg border transition-colors',
                img.kept ? 'border-primary ring-primary/30 ring-2' : 'border-border/70',
              )}
            >
              <div className="relative">
                <ImageThumb url={img.url} className="aspect-square w-full" />
                {usable && (
                  <Badge className="bg-highlight text-highlight-foreground absolute top-1.5 left-1.5 text-[10px]">
                    可用
                  </Badge>
                )}
              </div>
              <div className="space-y-2 p-2">
                <div className="flex items-center justify-between">
                  <StarRating
                    value={img.score}
                    disabled={score.isPending}
                    onChange={(n) => void setScore(img.id, n)}
                  />
                  <span className="text-muted-foreground/60 font-mono text-[10px]">
                    #{img.seed}
                  </span>
                </div>
                <Button
                  size="sm"
                  variant={img.kept ? 'default' : 'outline'}
                  disabled={keep.isPending}
                  onClick={() => void toggleKeep(img.id, img.kept)}
                  className="h-7 w-full text-xs"
                >
                  {img.kept ? (
                    <>
                      <CheckIcon className="size-3.5" />
                      已保留
                    </>
                  ) : (
                    <>
                      <BookmarkIcon className="size-3.5" />
                      保留
                    </>
                  )}
                </Button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
