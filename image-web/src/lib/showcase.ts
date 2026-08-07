import type { AdminImage, ImageShowcaseUpdate } from '@/api/admin'

const SHOWCASE_IMAGE_TYPES = new Set(['白底', '场景', '卖点'])

export function showcasePayload(
  isPublic: boolean,
  downloadAllowed: boolean,
): ImageShowcaseUpdate {
  return {
    is_public: isPublic,
    download_allowed: isPublic && downloadAllowed,
  }
}

export function showcaseIneligibility(
  image: Pick<
    AdminImage,
    'status' | 'moderation_status' | 'prompt' | 'image_type'
  >,
): string | null {
  if (image.status !== '成功') return '只有生成成功的图片可以公开展示'
  if (image.moderation_status !== 'normal') return '已屏蔽图片不能公开展示'
  if (!image.prompt.trim()) return '缺少用户提示词，不能公开展示'
  if (!image.image_type || !SHOWCASE_IMAGE_TYPES.has(image.image_type)) {
    return '缺少有效图片类型，不能公开展示'
  }
  return null
}
