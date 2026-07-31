import type { ModelConfig } from '@/api/admin'
import { encryptSecret } from '@/api/crypto'
import type { components } from '@/api/schema'

export type ModelType = components['schemas']['ModelType']
export type ProviderType = components['schemas']['ProviderType']

export const BUILT_IN_MODEL_IDS = [
  'gpt-image-2',
  'wan2.7-image-pro',
  'doubao-chat',
] as const

export interface ProviderFormDefinition {
  label: string
  modelType: ModelType
  credentialFields: readonly (
    | 'standardApiKeys'
    | 'fourKApiKey'
    | 'apiKey'
  )[]
  extraFields: readonly (
    | 'inputFidelity'
    | 'responseFormat'
    | 'watermark'
    | 'thinkingDisabled'
  )[]
}

export const PROVIDER_FORM_DEFINITIONS: Record<
  ProviderType,
  ProviderFormDefinition
> = {
  openai_compat_image: {
    label: 'OpenAI 兼容图片',
    modelType: 'image',
    credentialFields: ['standardApiKeys', 'fourKApiKey'],
    extraFields: ['inputFidelity', 'responseFormat'],
  },
  dashscope_wan_image: {
    label: '阿里云百炼 Wan',
    modelType: 'image',
    credentialFields: ['apiKey'],
    extraFields: ['watermark'],
  },
  openai_compat_chat: {
    label: 'OpenAI 兼容 Chat',
    modelType: 'chat',
    credentialFields: ['apiKey'],
    extraFields: ['thinkingDisabled'],
  },
}

export function providersForModelType(type: ModelType): ProviderType[] {
  return (Object.keys(PROVIDER_FORM_DEFINITIONS) as ProviderType[]).filter(
    (provider) => PROVIDER_FORM_DEFINITIONS[provider].modelType === type,
  )
}

export interface ModelFormFields {
  name: string
  displayName: string
  modelType: ModelType
  providerType: ProviderType
  baseUrl: string
  upstreamModel: string
  unitCost: string
  enabled: boolean
  standardApiKeys: string
  fourKApiKey: string
  apiKey: string
  inputFidelity: string
  responseFormat: string
  watermark: boolean
  thinkingDisabled: boolean
}

export function providerDefaults(providerType: ProviderType) {
  return providerType === 'openai_compat_image'
    ? {
        inputFidelity: 'high',
        responseFormat: 'b64_json',
        watermark: false,
        thinkingDisabled: false,
      }
    : providerType === 'dashscope_wan_image'
      ? {
          inputFidelity: '',
          responseFormat: '',
          watermark: false,
          thinkingDisabled: false,
        }
      : {
          inputFidelity: '',
          responseFormat: '',
          watermark: false,
          thinkingDisabled: true,
        }
}

export function modelFormFields(model?: ModelConfig): ModelFormFields {
  const providerType = model?.provider_type ?? 'openai_compat_image'
  const defaults = providerDefaults(providerType)
  return {
    name: model?.name ?? '',
    displayName: model?.display_name ?? '',
    modelType: model?.model_type ?? 'image',
    providerType,
    baseUrl: model?.base_url ?? '',
    upstreamModel: model?.model ?? '',
    unitCost: model?.unit_cost ?? '0',
    enabled: model?.enabled ?? false,
    standardApiKeys: '',
    fourKApiKey: '',
    apiKey: '',
    inputFidelity: String(
      model?.extra.input_fidelity ?? defaults.inputFidelity,
    ),
    responseFormat: String(
      model?.extra.response_format ?? defaults.responseFormat,
    ),
    watermark:
      typeof model?.extra.watermark === 'boolean'
        ? model.extra.watermark
        : defaults.watermark,
    thinkingDisabled:
      typeof model?.extra.thinking_disabled === 'boolean'
        ? model.extra.thinking_disabled
        : defaults.thinkingDisabled,
  }
}

export function modelRuntimeFingerprint(fields: ModelFormFields): string {
  const definition = PROVIDER_FORM_DEFINITIONS[fields.providerType]
  const secrets = Object.fromEntries(
    definition.credentialFields.map((field) => [field, fields[field]]),
  )
  const extra = Object.fromEntries(
    definition.extraFields.map((field) => [field, fields[field]]),
  )
  return JSON.stringify({
    name: fields.name.trim(),
    modelType: fields.modelType,
    providerType: fields.providerType,
    baseUrl: fields.baseUrl.trim().replace(/\/+$/, ''),
    upstreamModel: fields.upstreamModel.trim(),
    secrets,
    extra,
  })
}

export function plaintextCredentials(
  fields: ModelFormFields,
): Record<string, string | string[]> | undefined {
  if (fields.providerType === 'openai_compat_image') {
    const standardApiKeys = fields.standardApiKeys
      .split('\n')
      .map((key) => key.trim())
      .filter(Boolean)
    const fourKApiKey = fields.fourKApiKey.trim()
    if (standardApiKeys.length === 0 && !fourKApiKey) return undefined
    if (standardApiKeys.length === 0) {
      throw new Error('请至少填写一个标准图片 API Key')
    }
    return {
      standard_api_keys: standardApiKeys,
      ...(fourKApiKey ? { four_k_api_key: fourKApiKey } : {}),
    }
  }
  const apiKey = fields.apiKey.trim()
  return apiKey ? { api_key: apiKey } : undefined
}

export async function encryptModelCredentials(
  fields: ModelFormFields,
  encrypt: (secret: string) => Promise<string> = encryptSecret,
): Promise<Record<string, string | string[]> | undefined> {
  const plaintext = plaintextCredentials(fields)
  if (!plaintext) return undefined
  const encrypted: Record<string, string | string[]> = {}
  for (const [field, value] of Object.entries(plaintext)) {
    encrypted[field] = Array.isArray(value)
      ? await Promise.all(value.map((secret) => encrypt(secret)))
      : await encrypt(value)
  }
  return encrypted
}

export function modelExtra(fields: ModelFormFields): Record<string, unknown> {
  switch (fields.providerType) {
    case 'openai_compat_image':
      return {
        input_fidelity: fields.inputFidelity,
        response_format: fields.responseFormat,
      }
    case 'dashscope_wan_image':
      return { watermark: fields.watermark }
    case 'openai_compat_chat':
      return { thinking_disabled: fields.thinkingDisabled }
  }
}

export type VerificationState =
  | { kind: 'untested' }
  | { kind: 'testing' }
  | { kind: 'passed'; proof: string; testedFingerprint: string }
  | { kind: 'failed'; message: string }
