import type { components } from '@/api/schema'

type Schemas = components['schemas']

export type ImageToolSource =
  | { kind: 'upload'; uploadId: string; previewUrl?: string }
  | { kind: 'generated'; imageKey: string; previewUrl?: string }

export type BackgroundChoice =
  | { kind: 'description'; description: string }
  | { kind: 'reference'; uploadId: string; instruction: string }

export interface BackgroundReplaceInput {
  source: ImageToolSource
  background: BackgroundChoice
}

export type BackgroundReplaceBody = Schemas['BackgroundReplaceRequest']
export type ReversePromptBody = Schemas['ReversePromptRequest']
export type ReversePromptResult = Schemas['ReversePromptResult']

export interface BackgroundWorkbenchPrefill {
  source_kind?: 'upload' | 'generated'
  source_id?: string
  source_url?: string
  background_kind?: 'description' | 'reference'
  background_description?: string
  background_reference_id?: string
  background_reference_url?: string
  background_instruction?: string
}

export interface BackgroundReferenceSelection {
  uploadId: string
  previewUrl: string
}

export interface BackgroundWorkbenchState {
  source: ImageToolSource | null
  backgroundMode: 'description' | 'reference'
  description: string
  reference: BackgroundReferenceSelection | null
  instruction: string
}

function sourceBody(source: ImageToolSource) {
  if (source.kind === 'upload') {
    return { kind: 'upload' as const, upload_id: source.uploadId }
  }
  return { kind: 'generated' as const, image_key: source.imageKey }
}

export function buildBackgroundReplaceBody(
  input: BackgroundReplaceInput,
): BackgroundReplaceBody {
  const background =
    input.background.kind === 'description'
      ? {
          kind: 'description' as const,
          description: input.background.description.trim(),
        }
      : {
          kind: 'reference' as const,
          upload_id: input.background.uploadId,
          instruction: input.background.instruction.trim(),
        }
  return { source: sourceBody(input.source), background }
}

export function buildReversePromptBody(
  source: ImageToolSource,
): ReversePromptBody {
  return { source: sourceBody(source) }
}

export function backgroundWorkbenchStateFromPrefill(
  prefill: BackgroundWorkbenchPrefill | undefined,
  uploadPreview: (uploadId: string) => string,
): BackgroundWorkbenchState {
  if (!prefill) {
    return {
      source: null,
      backgroundMode: 'description',
      description: '',
      reference: null,
      instruction: '',
    }
  }

  let source: ImageToolSource | null = null
  if (prefill.source_kind) {
    if (!prefill.source_id) throw new Error('换背景预填缺少商品图标识')
    source =
      prefill.source_kind === 'upload'
        ? {
            kind: 'upload',
            uploadId: prefill.source_id,
            previewUrl:
              prefill.source_url ?? uploadPreview(prefill.source_id),
          }
        : {
            kind: 'generated',
            imageKey: prefill.source_id,
            previewUrl: prefill.source_url,
          }
  }

  const backgroundMode = prefill.background_kind ?? 'description'
  let reference: BackgroundReferenceSelection | null = null
  if (backgroundMode === 'reference') {
    if (!prefill.background_reference_id) {
      throw new Error('换背景预填缺少背景参考图标识')
    }
    reference = {
      uploadId: prefill.background_reference_id,
      previewUrl:
        prefill.background_reference_url ??
        uploadPreview(prefill.background_reference_id),
    }
  }

  return {
    source,
    backgroundMode,
    description: prefill.background_description ?? '',
    reference,
    instruction: prefill.background_instruction ?? '',
  }
}

const SUPPORTED_RATIOS = [
  ['1:1', 1],
  ['3:4', 3 / 4],
  ['4:3', 4 / 3],
  ['9:16', 9 / 16],
  ['16:9', 16 / 9],
] as const

export function closestSupportedRatio(width: number, height: number): string {
  if (width <= 0 || height <= 0) throw new Error('图片尺寸无效')
  const actual = width / height
  let closest: (typeof SUPPORTED_RATIOS)[number] =
    SUPPORTED_RATIOS[0]
  for (const candidate of SUPPORTED_RATIOS.slice(1)) {
    if (
      Math.abs(actual - candidate[1]) <
      Math.abs(actual - closest[1])
    ) {
      closest = candidate
    }
  }
  return closest[0]
}
