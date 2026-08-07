import { useState } from 'react'
import { EyeIcon, EyeOffIcon } from 'lucide-react'
import { toast } from 'sonner'

import {
  useUpdateAdminImageShowcase,
  type AdminImage,
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
import { Switch } from '@/components/ui/switch'
import { showcaseIneligibility, showcasePayload } from '@/lib/showcase'

export function ShowcaseDialog({ image }: { image: AdminImage }) {
  const [open, setOpen] = useState(false)
  const [downloadAllowed, setDownloadAllowed] = useState(false)
  const mutation = useUpdateAdminImageShowcase()
  const eligibilityError = showcaseIneligibility(image)

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (next) setDownloadAllowed(image.showcase_download_allowed)
  }

  async function update(isPublic: boolean) {
    try {
      await mutation.mutateAsync({
        imageId: image.image_id,
        body: showcasePayload(isPublic, downloadAllowed),
      })
      toast.success(isPublic ? '公开展示设置已更新' : '已取消公开展示')
      setOpen(false)
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : '更新公开展示设置失败',
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant={image.is_public_showcase ? 'outline' : 'default'}
          disabled={!image.is_public_showcase && Boolean(eligibilityError)}
          title={eligibilityError ?? undefined}
        >
          {image.is_public_showcase ? (
            <EyeIcon className="size-3.5" />
          ) : (
            <EyeOffIcon className="size-3.5" />
          )}
          {image.is_public_showcase ? '展示设置' : '公开展示'}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>
            {image.is_public_showcase ? '调整公开展示' : '公开展示这张图片'}
          </DialogTitle>
          <DialogDescription>
            图片和用户提示词会显示在“看看实朴出的图”；同一张压缩预览图也会用于网站首页。
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-4 sm:grid-cols-[11rem_1fr]">
          <img
            src={image.url}
            alt="待公开展示图片"
            className="max-h-64 w-full rounded-xl bg-wb-surface-4 object-contain ring-1 ring-wb-line-1"
          />
          <div className="min-w-0 space-y-3">
            <div>
              <p className="text-xs font-medium text-wb-ink-5">用户提示词</p>
              <p className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-wb-ink-2">
                {image.prompt}
              </p>
            </div>
            <div className="flex items-center justify-between gap-3 rounded-xl bg-wb-surface-3 px-3 py-3">
              <Label htmlFor={`showcase-download-${image.image_id}`}>
                <span className="block">允许下载原图</span>
                <span className="mt-0.5 block text-xs font-normal text-wb-ink-6">
                  仅影响 /home 的系统下载按钮
                </span>
              </Label>
              <Switch
                id={`showcase-download-${image.image_id}`}
                checked={downloadAllowed}
                onCheckedChange={setDownloadAllowed}
              />
            </div>
          </div>
        </div>

        <DialogFooter className="sm:justify-between">
          {image.is_public_showcase ? (
            <Button
              type="button"
              variant="destructive"
              disabled={mutation.isPending}
              onClick={() => void update(false)}
            >
              取消展示
            </Button>
          ) : (
            <span />
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              取消
            </Button>
            <Button
              type="button"
              disabled={mutation.isPending || Boolean(eligibilityError)}
              onClick={() => void update(true)}
            >
              {mutation.isPending ? '保存中…' : '保存并展示'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
