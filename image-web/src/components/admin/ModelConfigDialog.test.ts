import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import type { ModelConfig } from '@/api/admin'
import {
  ProviderFields,
  VerificationPanel,
} from '@/components/admin/ModelConfigDialog'
import {
  BUILT_IN_MODEL_IDS,
  PROVIDER_FORM_DEFINITIONS,
  encryptModelCredentials,
  modelFormFields,
  modelRuntimeFingerprint,
  providersForModelType,
  type ModelFormFields,
} from '@/lib/model-config'

const existing: ModelConfig = {
  name: 'gpt-image-2',
  display_name: 'GPT Image 2',
  model_type: 'image',
  provider_type: 'openai_compat_image',
  base_url: 'https://images.example/v1',
  model: 'gpt-image-2',
  unit_cost: '0.0500',
  enabled: true,
  is_default: true,
  revision: 3,
  verified_at: '2026-07-30T12:00:00Z',
  extra: { input_fidelity: 'high', response_format: 'b64_json' },
  credentials: {
    has_credentials: true,
    configured_fields: {
      standard_api_keys: true,
      four_k_api_key: true,
    },
  },
}

function withFields(
  patch: Partial<ModelFormFields> = {},
): ModelFormFields {
  return { ...modelFormFields(), ...patch }
}

describe('typed model provider form', () => {
  it('defines only the GPT, Wan, and Doubao initial model identities', () => {
    expect(BUILT_IN_MODEL_IDS).toEqual([
      'gpt-image-2',
      'nano-banana-2',
      'wan2.7-image-pro',
      'doubao-chat',
      'doubao-vision',
    ])
  })

  it('filters providers by model type and exposes exact allowlisted fields', () => {
    expect(providersForModelType('image')).toEqual([
      'openai_compat_image',
      'gemini_native_image',
      'dashscope_wan_image',
    ])
    expect(providersForModelType('chat')).toEqual([
      'openai_compat_chat',
    ])
    expect(providersForModelType('vision')).toEqual([
      'openai_compat_chat',
    ])
    expect(PROVIDER_FORM_DEFINITIONS.openai_compat_image).toMatchObject({
      credentialFields: ['standardApiKeys', 'fourKApiKey'],
      extraFields: ['inputFidelity', 'responseFormat'],
    })
    expect(PROVIDER_FORM_DEFINITIONS.dashscope_wan_image).toMatchObject({
      credentialFields: ['apiKey'],
      extraFields: ['watermark'],
    })
    expect(PROVIDER_FORM_DEFINITIONS.gemini_native_image).toMatchObject({
      credentialFields: ['apiKeys'],
      extraFields: [],
    })
    expect(PROVIDER_FORM_DEFINITIONS.openai_compat_chat).toMatchObject({
      modelTypes: ['chat', 'vision'],
      credentialFields: ['apiKey'],
      extraFields: ['thinkingDisabled'],
    })
  })

  it('encrypts every standard key and optional 4K key independently', async () => {
    const encrypt = vi.fn(async (secret: string) => `cipher:${secret}`)
    const fields = withFields({
      standardApiKeys: 'key-a\nkey-b',
      fourKApiKey: 'key-4k',
    })

    await expect(encryptModelCredentials(fields, encrypt)).resolves.toEqual({
      standard_api_keys: ['cipher:key-a', 'cipher:key-b'],
      four_k_api_key: 'cipher:key-4k',
    })
    expect(encrypt.mock.calls.map(([secret]) => secret)).toEqual([
      'key-a',
      'key-b',
      'key-4k',
    ])
    expect(encrypt).not.toHaveBeenCalledWith('key-a\nkey-b')
    expect(fields.standardApiKeys).toBe('key-a\nkey-b')
  })

  it('encrypts every Gemini key line independently', async () => {
    const encrypt = vi.fn(async (secret: string) => `cipher:${secret}`)
    const fields = withFields({
      providerType: 'gemini_native_image',
      apiKeys: 'nano-a\n\nnano-b',
    })

    await expect(encryptModelCredentials(fields, encrypt)).resolves.toEqual({
      api_keys: ['cipher:nano-a', 'cipher:nano-b'],
    })
    expect(encrypt.mock.calls.map(([secret]) => secret)).toEqual([
      'nano-a',
      'nano-b',
    ])
  })

  it('keeps replacement secrets blank in edit mode and shows configured state', () => {
    const fields = modelFormFields(existing)
    expect(fields.standardApiKeys).toBe('')
    expect(fields.fourKApiKey).toBe('')
    expect(fields.apiKey).toBe('')

    const html = renderToStaticMarkup(
      createElement(ProviderFields, {
        fields,
        configured: existing.credentials.configured_fields,
        onRuntimeChange: () => undefined,
      }),
    )
    expect(html).toContain('已配置；留空则保留')
    expect(html).not.toContain('cipher')
  })

  it('invalidates proof fingerprints for runtime and credential edits only', () => {
    const fields = withFields({
      name: 'gpt-image-2',
      displayName: 'GPT Image 2',
      baseUrl: 'https://images.example/v1',
      upstreamModel: 'gpt-image-2',
      standardApiKeys: 'secret',
    })
    const fingerprint = modelRuntimeFingerprint(fields)
    expect(
      modelRuntimeFingerprint({
        ...fields,
        displayName: 'New public name',
        unitCost: '99',
      }),
    ).toBe(fingerprint)
    expect(
      modelRuntimeFingerprint({ ...fields, baseUrl: 'https://other/v1' }),
    ).not.toBe(fingerprint)
    expect(
      modelRuntimeFingerprint({ ...fields, standardApiKeys: 'replacement' }),
    ).not.toBe(fingerprint)
  })

  it('renders real capability checks without deployment-protocol guidance', () => {
    const html = renderToStaticMarkup(
      createElement(VerificationPanel, {
        verification: {
          kind: 'passed',
          proof: 'proof',
          testedFingerprint: 'fingerprint',
        },
        checks: ['generate', 'edit'],
      }),
    )
    expect(html).toContain('真实能力测试')
    expect(html).toContain('generate · edit')
    expect(html).not.toMatch(/restart|\.env|重启|兼容协议/i)
  })
})
