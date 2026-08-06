const ACCEPTED_IMAGE_TYPES = new Set([
  'image/png',
  'image/jpeg',
  'image/webp',
])

export interface ChatImageFileSelection {
  accepted: File[]
  unsupportedCount: number
  overflowCount: number
  full: boolean
}

export function selectChatImageFiles(
  files: readonly File[],
  remainingSlots: number,
): ChatImageFileSelection {
  const availableSlots = Math.max(0, remainingSlots)
  const supported = files.filter((file) =>
    ACCEPTED_IMAGE_TYPES.has(file.type),
  )
  const accepted = supported.slice(0, availableSlots)

  return {
    accepted,
    unsupportedCount: files.length - supported.length,
    overflowCount: supported.length - accepted.length,
    full: availableSlots === 0 && supported.length > 0,
  }
}
