import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'

import {
  useCreateModel,
  useUpdateModel,
  type ModelConfig,
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const DEFAULT_PROVIDER_TYPE = 'openai_compat_image'
/** 环境变量名（UPPER_SNAKE）——用于挡住把真实密钥误填进「密钥变量」（验收⑦）。 */
const ENV_NAME_RE = /^[A-Z_][A-Z0-9_]*$/

interface Fields {
  name: string
  unitCost: string
  providerType: string
  baseUrl: string
  model: string
  apiKeyEnv: string
}

function fieldsOf(model?: ModelConfig): Fields {
  return {
    name: model?.name ?? '',
    unitCost: model?.unit_cost ?? '',
    providerType: model?.provider_type ?? DEFAULT_PROVIDER_TYPE,
    baseUrl: model?.base_url ?? '',
    model: model?.model ?? '',
    apiKeyEnv: model?.api_key_env ?? '',
  }
}

type Props = { trigger: ReactNode } & (
  | { mode: 'create' }
  | { mode: 'edit'; model: ModelConfig }
)

/**
 * 模型渠道配置的新增 / 编辑（ISSUE-0057）。承载「备用渠道切换」：填一行中转站连接
 * （类型 / base_url / 模型 / 密钥变量）。**密钥变量只收环境变量名，真实密钥仅存服务端环境变量**（验收⑦）。
 */
export function ModelConfigDialog(props: Props) {
  const { trigger, mode } = props
  const editing = mode === 'edit' ? props.model : undefined
  const [open, setOpen] = useState(false)
  const [f, setF] = useState<Fields>(() => fieldsOf(editing))
  const create = useCreateModel()
  const update = useUpdateModel()
  const pending = create.isPending || update.isPending

  function onOpenChange(next: boolean) {
    setOpen(next)
    if (next) setF(fieldsOf(editing))
  }

  function set<K extends keyof Fields>(key: K, value: Fields[K]) {
    setF((prev) => ({ ...prev, [key]: value }))
  }

  async function submit() {
    const name = f.name.trim()
    if (mode === 'create' && !name) {
      toast.error('请填模型名')
      return
    }
    const cost = Number(f.unitCost)
    if (!Number.isFinite(cost) || cost < 0) {
      toast.error('单价需为非负数')
      return
    }
    const apiKeyEnv = f.apiKeyEnv.trim()
    if (apiKeyEnv && !ENV_NAME_RE.test(apiKeyEnv)) {
      toast.error('「密钥变量」请填环境变量名（大写字母/数字/下划线），而非密钥本身')
      return
    }
    const conn = {
      provider_type: f.providerType.trim() || DEFAULT_PROVIDER_TYPE,
      base_url: f.baseUrl.trim(),
      model: f.model.trim(),
      api_key_env: apiKeyEnv,
    }
    try {
      if (mode === 'create') {
        await create.mutateAsync({ name, unit_cost: cost, enabled: true, ...conn })
        toast.success(`已新增模型「${name}」`)
      } else {
        await update.mutateAsync({ name: editing!.name, patch: { unit_cost: cost, ...conn } })
        toast.success(`已更新「${editing!.name}」`)
      }
      setOpen(false)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '保存失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? '新增模型渠道' : '编辑模型渠道'}</DialogTitle>
          <DialogDescription>
            配置出图 Provider 的连接。真实密钥仅存服务端环境变量，此处只填「密钥变量」（环境变量名）。
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="mc-name">模型名</Label>
            {mode === 'create' ? (
              <Input
                id="mc-name"
                value={f.name}
                onChange={(e) => set('name', e.target.value)}
                placeholder="如 gpt-image-2-backup"
                autoFocus
              />
            ) : (
              <p className="font-mono text-sm text-muted-foreground">{editing!.name}</p>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="mc-provider">Provider 类型</Label>
              <Input
                id="mc-provider"
                value={f.providerType}
                onChange={(e) => set('providerType', e.target.value)}
                placeholder={DEFAULT_PROVIDER_TYPE}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="mc-cost">单价（¥ / 张）</Label>
              <Input
                id="mc-cost"
                type="number"
                min="0"
                step="0.01"
                value={f.unitCost}
                onChange={(e) => set('unitCost', e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="mc-base-url">Base URL</Label>
            <Input
              id="mc-base-url"
              value={f.baseUrl}
              onChange={(e) => set('baseUrl', e.target.value)}
              placeholder="https://中转站/v1（留空则回落 .env）"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="mc-model">模型 ID</Label>
            <Input
              id="mc-model"
              value={f.model}
              onChange={(e) => set('model', e.target.value)}
              placeholder="如 gpt-image-2"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="mc-key-env">密钥变量（环境变量名）</Label>
            <Input
              id="mc-key-env"
              className="font-mono"
              value={f.apiKeyEnv}
              onChange={(e) => set('apiKeyEnv', e.target.value)}
              placeholder="如 APINEBULA_API_KEY"
            />
            <p className="text-xs text-muted-foreground">
              填服务端环境变量的名字，不是密钥本身。留空则回落 .env 默认连接。
            </p>
          </div>

          <DialogFooter>
            <Button type="submit" disabled={pending}>
              {pending ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
