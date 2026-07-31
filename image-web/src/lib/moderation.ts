import type { ImageModerationUpdate } from '@/api/admin'

type ModerationReason = NonNullable<ImageModerationUpdate['reason']>
type ModerationTargetStatus = ImageModerationUpdate['status']

export function moderationPayload(
  status: ModerationTargetStatus,
  reason: ModerationReason | '',
  note: string,
): ImageModerationUpdate | null {
  if (status === 'blocked') {
    if (!reason) return null
    return {
      status,
      reason,
      note: note.trim(),
    }
  }
  return {
    status: 'normal',
    reason: null,
    note: null,
  }
}
