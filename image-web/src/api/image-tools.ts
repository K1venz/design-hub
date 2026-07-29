import { useMutation } from '@tanstack/react-query'

import { api } from '@/api/client'
import { errorMessage } from '@/api/errors'
import { postJson } from '@/api/listing'
import {
  buildBackgroundReplaceBody,
  buildReversePromptBody,
  type BackgroundReplaceInput,
  type ImageToolSource,
  type ReversePromptResult,
} from '@/lib/image-tools'

export function useBackgroundReplace() {
  return useMutation({
    mutationFn: (input: BackgroundReplaceInput) =>
      postJson(
        '/listing/background-replace',
        buildBackgroundReplaceBody(input),
      ),
  })
}

export async function reverseImagePrompt(
  source: ImageToolSource,
): Promise<ReversePromptResult> {
  const { data, error } = await api.POST('/image-prompts/reverse', {
    body: buildReversePromptBody(source),
  })
  if (error || !data) {
    throw new Error(errorMessage(error, '反推提示词失败'))
  }
  return data
}

export function useReverseImagePrompt() {
  return useMutation({ mutationFn: reverseImagePrompt })
}
