import { useState } from 'react'
import { CheckIcon, PlusIcon } from 'lucide-react'
import { toast } from 'sonner'

import { useAddItem, useOpenRevision, useRevisions, useToggleItem } from '@/api/revision'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export function RevisionTab({ projectId }: { projectId: number }) {
  const revisions = useRevisions(projectId)
  const open = useOpenRevision(projectId)
  const addItem = useAddItem(projectId)
  const toggle = useToggleItem(projectId)
  const [drafts, setDrafts] = useState<Record<number, string>>({})

  async function openRevision() {
    try {
      await open.mutateAsync()
      toast.success('已开改稿单')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '开改稿单失败')
    }
  }
  async function submitItem(revisionId: number) {
    const text = (drafts[revisionId] ?? '').trim()
    if (!text) return
    try {
      await addItem.mutateAsync({ revisionId, text })
      setDrafts((d) => ({ ...d, [revisionId]: '' }))
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '添加条目失败')
    }
  }
  async function toggleItem(revisionId: number, seq: number, done: boolean) {
    try {
      await toggle.mutateAsync({ revisionId, seq, done })
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '勾选失败')
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">逐条改稿、勾选完成；全部完成后方可交付（管理者可强制）。</p>
        <Button onClick={() => void openRevision()} disabled={open.isPending}>
          <PlusIcon className="size-4" />
          开改稿单
        </Button>
      </div>

      {revisions.isLoading ? (
        <Card className="space-y-3 p-6">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-9 w-full" />
        </Card>
      ) : revisions.data && revisions.data.length > 0 ? (
        revisions.data.map((r) => {
          const remaining = r.items.filter((i) => !i.done).length
          return (
            <Card key={r.id} className="space-y-4 p-5">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">第 {r.round_no} 轮改稿</h3>
                <Badge
                  variant="outline"
                  className={
                    r.status === '已完成'
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-amber-200 bg-amber-50 text-amber-700'
                  }
                >
                  {r.status}
                </Badge>
                {remaining > 0 && (
                  <span className="text-muted-foreground text-xs">{remaining} 条未完成</span>
                )}
              </div>

              <ul className="space-y-1.5">
                {r.items.map((item) => (
                  <li key={item.seq} className="flex items-start gap-2.5">
                    <button
                      type="button"
                      disabled={toggle.isPending}
                      onClick={() => void toggleItem(r.id, item.seq, !item.done)}
                      className={cn(
                        'mt-0.5 flex size-4.5 shrink-0 items-center justify-center rounded border transition-colors',
                        item.done
                          ? 'border-primary bg-primary text-primary-foreground'
                          : 'border-input hover:border-primary',
                      )}
                      aria-label={item.done ? '取消完成' : '标记完成'}
                    >
                      {item.done && <CheckIcon className="size-3" />}
                    </button>
                    <span
                      className={cn(
                        'text-sm',
                        item.done ? 'text-muted-foreground line-through' : 'text-foreground',
                      )}
                    >
                      {item.text}
                    </span>
                  </li>
                ))}
                {r.items.length === 0 && (
                  <li className="text-muted-foreground text-sm">还没有改稿条目。</li>
                )}
              </ul>

              <form
                className="flex gap-2"
                onSubmit={(e) => {
                  e.preventDefault()
                  void submitItem(r.id)
                }}
              >
                <Input
                  value={drafts[r.id] ?? ''}
                  onChange={(e) => setDrafts((d) => ({ ...d, [r.id]: e.target.value }))}
                  placeholder="新增改稿条目，如：主图文案换行"
                  className="h-9"
                />
                <Button
                  type="submit"
                  variant="outline"
                  size="sm"
                  disabled={addItem.isPending || !(drafts[r.id] ?? '').trim()}
                >
                  加条目
                </Button>
              </form>
            </Card>
          )
        })
      ) : (
        <Card className="text-muted-foreground py-12 text-center text-sm">
          还没有改稿单。客户审稿后开一单逐条跟踪。
        </Card>
      )}
    </div>
  )
}
