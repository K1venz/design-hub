import { useRef, useState, type ReactNode } from 'react'
import { CheckCircle2Icon, Loader2Icon, ShieldCheckIcon } from 'lucide-react'
import { toast } from 'sonner'

import {
  useCreateModel,
  useTestModel,
  useUpdateModel,
  type ModelCapabilityTestInput,
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
import { Switch } from '@/components/ui/switch'
import {
  PROVIDER_FORM_DEFINITIONS,
  encryptModelCredentials,
  modelExtra,
  modelFormFields,
  modelRuntimeFingerprint,
  plaintextCredentials,
  providerDefaults,
  providersForModelType,
  type ModelFormFields,
  type ModelType,
  type ProviderType,
  type VerificationState,
} from '@/lib/model-config'

type Props = { trigger: ReactNode } & (
  | { mode: 'create' }
  | { mode: 'edit'; model: ModelConfig }
)

export function ModelConfigDialog(props: Props) {
  const { trigger, mode } = props
  const editing = mode === 'edit' ? props.model : undefined
  const [open, setOpen] = useState(false)
  const [fields, setFields] = useState<ModelFormFields>(() =>
    modelFormFields(editing),
  )
  const fieldsRef = useRef(fields)
  const [verification, setVerification] = useState<VerificationState>({
    kind: 'untested',
  })
  const [checks, setChecks] = useState<string[]>([])
  const create = useCreateModel()
  const update = useUpdateModel()
  const test = useTestModel()
  const pending =
    create.isPending || update.isPending || verification.kind === 'testing'
  const currentFingerprint = modelRuntimeFingerprint(fields)
  const proofCurrent =
    verification.kind === 'passed' &&
    verification.testedFingerprint === currentFingerprint

  function replaceFields(
    next: ModelFormFields,
    invalidateProof: boolean,
  ) {
    fieldsRef.current = next
    setFields(next)
    if (invalidateProof) {
      setVerification({ kind: 'untested' })
      setChecks([])
    }
  }

  function setRuntime<K extends keyof ModelFormFields>(
    key: K,
    value: ModelFormFields[K],
  ) {
    replaceFields({ ...fieldsRef.current, [key]: value }, true)
  }

  function setCosmetic<K extends 'displayName' | 'unitCost'>(
    key: K,
    value: ModelFormFields[K],
  ) {
    replaceFields({ ...fieldsRef.current, [key]: value }, false)
  }

  function changeModelType(modelType: ModelType) {
    const providerType = providersForModelType(modelType)[0]
    replaceFields(
      {
        ...fieldsRef.current,
        modelType,
        providerType,
        standardApiKeys: '',
        apiKeys: '',
        fourKApiKey: '',
        apiKey: '',
        ...providerDefaults(providerType),
      },
      true,
    )
  }

  function changeProvider(providerType: ProviderType) {
    replaceFields(
      {
        ...fieldsRef.current,
        providerType,
        standardApiKeys: '',
        apiKeys: '',
        fourKApiKey: '',
        apiKey: '',
        ...providerDefaults(providerType),
      },
      true,
    )
  }

  function resetForm() {
    const next = modelFormFields(editing)
    fieldsRef.current = next
    setFields(next)
    setVerification({ kind: 'untested' })
    setChecks([])
    create.reset()
    update.reset()
    test.reset()
  }

  function onOpenChange(next: boolean) {
    setOpen(next)
    resetForm()
  }

  function validate() {
    if (!fields.name.trim()) throw new Error('请填写稳定模型 ID')
    if (!fields.displayName.trim()) throw new Error('请填写展示名称')
    if (!fields.baseUrl.trim()) throw new Error('请填写 Base URL')
    if (!fields.upstreamModel.trim()) throw new Error('请填写上游模型 ID')
    const unitCost = Number(fields.unitCost)
    if (!Number.isFinite(unitCost) || unitCost < 0) {
      throw new Error('内部单价必须是非负数')
    }
    if (
      mode === 'create' &&
      plaintextCredentials(fields) === undefined
    ) {
      throw new Error('请填写此 Provider 所需的凭据')
    }
    return unitCost
  }

  async function testConfiguration() {
    if (verification.kind === 'testing') return
    try {
      validate()
      const fingerprint = modelRuntimeFingerprint(fields)
      setVerification({ kind: 'testing' })
      const credentials = await encryptModelCredentials(fields)
      const body: ModelCapabilityTestInput = {
        name: fields.name.trim(),
        existing_model_name: editing?.name,
        model_type: fields.modelType,
        provider_type: fields.providerType,
        base_url: fields.baseUrl.trim(),
        model: fields.upstreamModel.trim(),
        credentials,
        extra: modelExtra(fields),
      }
      const result = await test.mutateAsync(body)
      if (modelRuntimeFingerprint(fieldsRef.current) !== fingerprint) {
        setVerification({ kind: 'untested' })
        return
      }
      setChecks(result.checks)
      setVerification({
        kind: 'passed',
        proof: result.verification_proof,
        testedFingerprint: fingerprint,
      })
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : '配置测试失败，请检查连接字段与凭据'
      setVerification({ kind: 'failed', message })
      setChecks([])
    }
  }

  async function submit() {
    try {
      const unitCost = validate()
      if (!proofCurrent || verification.kind !== 'passed') {
        throw new Error('请先测试当前配置并通过全部能力检查')
      }
      const credentials = await encryptModelCredentials(fields)
      const connection = {
        display_name: fields.displayName.trim(),
        model_type: fields.modelType,
        provider_type: fields.providerType,
        base_url: fields.baseUrl.trim(),
        model: fields.upstreamModel.trim(),
        unit_cost: unitCost,
        enabled: fields.enabled,
        extra: modelExtra(fields),
        verification_proof: verification.proof,
      }
      if (mode === 'create') {
        if (!credentials) throw new Error('请填写此 Provider 所需的凭据')
        await create.mutateAsync({
          name: fields.name.trim(),
          credentials,
          ...connection,
        })
        toast.success(`已创建「${fields.displayName.trim()}」，运行时立即可用`)
      } else {
        await update.mutateAsync({
          name: editing!.name,
          patch: {
            ...connection,
            ...(credentials ? { credentials } : {}),
          },
        })
        toast.success(`已更新「${fields.displayName.trim()}」，运行时立即生效`)
      }
      setOpen(false)
      resetForm()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存失败')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {mode === 'create' ? '新增模型配置' : '编辑模型配置'}
          </DialogTitle>
          <DialogDescription>
            连接字段保存后立即生效。所有凭据会在浏览器中逐项独立加密，
            编辑时留空表示保留服务端现有凭据。
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault()
            void submit()
          }}
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="稳定模型 ID" htmlFor="mc-name">
              {mode === 'create' ? (
                <Input
                  id="mc-name"
                  value={fields.name}
                  onChange={(event) =>
                    setRuntime('name', event.target.value)
                  }
                  placeholder="例如 gpt-image-2"
                  autoFocus
                />
              ) : (
                <p className="rounded-xl bg-wb-surface-1 px-3 py-2 font-mono text-sm">
                  {fields.name}
                </p>
              )}
            </Field>
            <Field label="展示名称" htmlFor="mc-display-name">
              <Input
                id="mc-display-name"
                value={fields.displayName}
                onChange={(event) =>
                  setCosmetic('displayName', event.target.value)
                }
                placeholder="用户看到的模型名称"
              />
            </Field>
            <Field label="模型类型" htmlFor="mc-model-type">
              <select
                id="mc-model-type"
                value={fields.modelType}
                onChange={(event) =>
                  changeModelType(event.target.value as ModelType)
                }
                className="h-10 w-full rounded-xl border border-input bg-transparent px-3 text-sm"
              >
                <option value="image">图片模型</option>
                <option value="chat">Chat 模型</option>
              </select>
            </Field>
            <Field label="Provider" htmlFor="mc-provider">
              <select
                id="mc-provider"
                value={fields.providerType}
                onChange={(event) =>
                  changeProvider(event.target.value as ProviderType)
                }
                className="h-10 w-full rounded-xl border border-input bg-transparent px-3 text-sm"
              >
                {providersForModelType(fields.modelType).map((provider) => (
                  <option key={provider} value={provider}>
                    {PROVIDER_FORM_DEFINITIONS[provider].label}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Base URL" htmlFor="mc-base-url">
              <Input
                id="mc-base-url"
                value={fields.baseUrl}
                onChange={(event) =>
                  setRuntime('baseUrl', event.target.value)
                }
                placeholder="https://api.example.com/v1"
              />
            </Field>
            <Field label="上游模型 ID" htmlFor="mc-upstream-model">
              <Input
                id="mc-upstream-model"
                value={fields.upstreamModel}
                onChange={(event) =>
                  setRuntime('upstreamModel', event.target.value)
                }
                placeholder="Provider 实际接收的 model"
              />
            </Field>
          </div>

          <ProviderFields
            fields={fields}
            configured={editing?.credentials.configured_fields ?? {}}
            onRuntimeChange={setRuntime}
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="内部单价（仅管理员可见）" htmlFor="mc-cost">
              <Input
                id="mc-cost"
                type="number"
                min="0"
                step="0.0001"
                value={fields.unitCost}
                onChange={(event) =>
                  setCosmetic('unitCost', event.target.value)
                }
              />
            </Field>
            <div className="flex items-center justify-between rounded-xl border border-wb-line-1 px-3 py-2">
              <div>
                <p className="text-sm font-medium">启用模型</p>
                <p className="text-xs text-muted-foreground">
                  仅通过当前配置测试后才能保存启用
                </p>
              </div>
              <Switch
                checked={fields.enabled}
                onCheckedChange={(enabled) =>
                  replaceFields({ ...fieldsRef.current, enabled }, false)
                }
              />
            </div>
          </div>

          <VerificationPanel
            verification={verification}
            checks={checks}
          />

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => void testConfiguration()}
            >
              {verification.kind === 'testing' ? (
                <Loader2Icon className="size-4 animate-spin" />
              ) : (
                <ShieldCheckIcon className="size-4" />
              )}
              测试当前配置
            </Button>
            <Button type="submit" disabled={pending || !proofCurrent}>
              {create.isPending || update.isPending ? '保存中…' : '保存配置'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function Field({
  label,
  htmlFor,
  children,
}: {
  label: string
  htmlFor: string
  children: ReactNode
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={htmlFor}>{label}</Label>
      {children}
    </div>
  )
}

export function ProviderFields({
  fields,
  configured,
  onRuntimeChange,
}: {
  fields: ModelFormFields
  configured: Record<string, boolean>
  onRuntimeChange: <K extends keyof ModelFormFields>(
    key: K,
    value: ModelFormFields[K],
  ) => void
}) {
  const configuredLabel = (key: string) =>
    configured[key] ? '已配置；留空则保留' : '尚未配置'

  return (
    <fieldset className="space-y-4 rounded-2xl border border-wb-line-1 p-4">
      <legend className="px-1 text-sm font-semibold">凭据与 Provider 参数</legend>
      {fields.providerType === 'openai_compat_image' ? (
        <>
          <Field label="标准图片 API Key 池" htmlFor="mc-standard-keys">
            <textarea
              id="mc-standard-keys"
              value={fields.standardApiKeys}
              onChange={(event) =>
                onRuntimeChange('standardApiKeys', event.target.value)
              }
              placeholder="每行一个 API Key"
              autoComplete="off"
              className="min-h-24 w-full rounded-xl border border-input bg-transparent px-3 py-2 font-mono text-sm"
            />
            <p className="text-xs text-muted-foreground">
              {configuredLabel('standard_api_keys')}；每个 Key 会独立加密。
            </p>
          </Field>
          <Field label="4K 专用 API Key（可选）" htmlFor="mc-four-k-key">
            <Input
              id="mc-four-k-key"
              type="password"
              value={fields.fourKApiKey}
              onChange={(event) =>
                onRuntimeChange('fourKApiKey', event.target.value)
              }
              placeholder={configuredLabel('four_k_api_key')}
              autoComplete="new-password"
            />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="编辑保真度" htmlFor="mc-input-fidelity">
              <select
                id="mc-input-fidelity"
                value={fields.inputFidelity}
                onChange={(event) =>
                  onRuntimeChange('inputFidelity', event.target.value)
                }
                className="h-10 w-full rounded-xl border border-input bg-transparent px-3 text-sm"
              >
                <option value="high">high</option>
                <option value="low">low</option>
              </select>
            </Field>
            <Field label="响应格式" htmlFor="mc-response-format">
              <select
                id="mc-response-format"
                value={fields.responseFormat}
                onChange={(event) =>
                  onRuntimeChange('responseFormat', event.target.value)
                }
                className="h-10 w-full rounded-xl border border-input bg-transparent px-3 text-sm"
              >
                <option value="b64_json">b64_json</option>
                <option value="url">url</option>
              </select>
            </Field>
          </div>
        </>
      ) : fields.providerType === 'gemini_native_image' ? (
        <Field label="Gemini API Key 池" htmlFor="mc-gemini-keys">
          <textarea
            id="mc-gemini-keys"
            value={fields.apiKeys}
            onChange={(event) =>
              onRuntimeChange('apiKeys', event.target.value)
            }
            placeholder="每行一个 API Key"
            autoComplete="off"
            className="min-h-24 w-full rounded-xl border border-input bg-transparent px-3 py-2 font-mono text-sm"
          />
          <p className="text-xs text-muted-foreground">
            {configuredLabel('api_keys')}；每个 Key 独立加密并自动轮换。
          </p>
        </Field>
      ) : (
        <Field label="API Key" htmlFor="mc-api-key">
          <Input
            id="mc-api-key"
            type="password"
            value={fields.apiKey}
            onChange={(event) =>
              onRuntimeChange('apiKey', event.target.value)
            }
            placeholder={configuredLabel('api_key')}
            autoComplete="new-password"
          />
        </Field>
      )}
      {fields.providerType === 'dashscope_wan_image' ? (
        <BooleanField
          label="生成结果添加水印"
          checked={fields.watermark}
          onChange={(value) => onRuntimeChange('watermark', value)}
        />
      ) : null}
      {fields.providerType === 'openai_compat_chat' ? (
        <BooleanField
          label="关闭上游思考模式"
          checked={fields.thinkingDisabled}
          onChange={(value) =>
            onRuntimeChange('thinkingDisabled', value)
          }
        />
      ) : null}
    </fieldset>
  )
}

function BooleanField({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label className="flex items-center justify-between rounded-xl bg-wb-surface-1 px-3 py-2 text-sm">
      {label}
      <Switch checked={checked} onCheckedChange={onChange} />
    </label>
  )
}

export function VerificationPanel({
  verification,
  checks,
}: {
  verification: VerificationState
  checks: string[]
}) {
  if (verification.kind === 'untested') {
    return (
      <div className="rounded-xl border border-wb-line-1 bg-wb-surface-1 p-3 text-sm text-muted-foreground">
        保存前请测试当前连接。图片模型会验证生成与编辑，Chat
        模型会验证流式文本与工具调用。
      </div>
    )
  }
  if (verification.kind === 'testing') {
    return (
      <div role="status" className="rounded-xl border border-wb-tint-line bg-wb-tint-3 p-3 text-sm">
        正在执行真实能力测试，请勿重复提交…
      </div>
    )
  }
  if (verification.kind === 'failed') {
    return (
      <div role="alert" className="rounded-xl border border-wb-red-line bg-wb-red-tint p-3 text-sm text-wb-red">
        {verification.message}
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
      <p className="flex items-center gap-1.5 font-medium">
        <CheckCircle2Icon className="size-4" />
        当前配置已通过真实能力测试
      </p>
      <p className="mt-1 text-xs">{checks.join(' · ')}</p>
    </div>
  )
}
