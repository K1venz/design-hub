import { useState } from 'react'
import { RotateCcwIcon, ShieldAlertIcon } from 'lucide-react'
import { toast } from 'sonner'

import {
  useModerateAdminImage,
  type ImageModerationUpdate,
} from '@/api/admin'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { moderationPayload } from '@/lib/moderation'

type ModerationReason = NonNullable<ImageModerationUpdate['reason']>
type ModerationTargetStatus = ImageModerationUpdate['status']

const REASONS: readonly {
  value: ModerationReason
  label: string
}[] = [
  { value: 'sexual', label: '色情低俗' },
  { value: 'violence', label: '暴力血腥' },
  { value: 'illegal', label: '违法内容' },
  { value: 'infringement', label: '侵权仿冒' },
  { value: 'other', label: '其他' },
]

interface ModerationImage {
  image_id: number
  url: string
  moderation_status: string
}

export function ModerationDialog({
  image,
}: {
  image: ModerationImage
}) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<ModerationReason | ''>('')
  const [note, setNote] = useState('')
  const mutation = useModerateAdminImage()
  const restoring = image.moderation_status === 'blocked'
  const targetStatus: ModerationTargetStatus = restoring
    ? 'normal'
    : 'blocked'

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (next) {
      setReason('')
      setNote('')
    }
  }

  async function submit() {
    const body = moderationPayload(targetStatus, reason, note)
    if (!body) {
      toast.error('请选择违规原因')
      return
    }
    try {
      await mutation.mutateAsync({
        imageId: image.image_id,
        body,
      })
      toast.success(restoring ? '图片已恢复' : '图片已屏蔽')
      setOpen(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : '审核操作失败',
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant={restoring ? 'outline' : 'destructive'}
        >
          {restoring ? (
            <RotateCcwIcon className="size-3.5" />
          ) : (
            <ShieldAlertIcon className="size-3.5" />
          )}
          {restoring ? '恢复图片' : '标记违规'}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>
            {restoring ? '恢复这张图片？' : '屏蔽这张图片？'}
          </DialogTitle>
          <DialogDescription>
            {restoring
              ? '恢复后，图片将重新允许普通用户预览、下载和继续编辑。'
              : '屏蔽后，普通用户将无法继续预览、下载或把它作为编辑源图。'}
          </DialogDescription>
        </DialogHeader>
        <img
          src={image.url}
          alt=""
          className="mx-auto max-h-56 rounded-xl object-contain ring-1 ring-wb-line-1"
        />
        {restoring ? null : (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor={`moderation-reason-${image.image_id}`}>
                违规原因
              </Label>
              <Select
                value={reason}
                onValueChange={(value) =>
                  setReason(value as ModerationReason)
                }
              >
                <SelectTrigger
                  id={`moderation-reason-${image.image_id}`}
                  className="w-full"
                >
                  <SelectValue placeholder="请选择原因" />
                </SelectTrigger>
                <SelectContent>
                  {REASONS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor={`moderation-note-${image.image_id}`}>
                内部备注（选填）
              </Label>
              <Textarea
                id={`moderation-note-${image.image_id}`}
                maxLength={500}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="仅管理员可见"
              />
            </div>
          </div>
        )}
        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => setOpen(false)}
          >
            取消
          </Button>
          <Button
            type="button"
            variant={restoring ? 'default' : 'destructive'}
            disabled={mutation.isPending}
            onClick={() => void submit()}
          >
            {mutation.isPending
              ? '处理中…'
              : restoring
                ? '确认恢复'
                : '确认屏蔽'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
