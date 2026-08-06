// @vitest-environment jsdom

import { createElement } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  ChatImageDropZone,
  type ChatImageFileSelection,
  selectChatImageFiles,
} from '@/components/chat/ChatImageDropZone'

const png = (name: string) =>
  new File(['png'], name, { type: 'image/png' })

const fileTransfer = (files: File[]) => ({
  files,
  types: ['Files'],
})

function renderDropZone(
  overrides: Partial<{
    disabled: boolean
    remainingSlots: number
    onSelection: (selection: ChatImageFileSelection) => void
  }> = {},
) {
  const onSelection = overrides.onSelection ?? vi.fn()
  const rendered = render(
    createElement(
      ChatImageDropZone,
      {
        disabled: overrides.disabled ?? false,
        remainingSlots: overrides.remainingSlots ?? 2,
        onSelection,
      },
      createElement(
        'section',
        { 'data-testid': 'composer-child' },
        'composer',
      ),
    ),
  )
  const zone = rendered.container.querySelector(
    '[data-chat-image-drop-zone]',
  )
  if (!zone) throw new Error('drop zone was not rendered')
  return { ...rendered, onSelection, zone }
}

afterEach(cleanup)

describe('selectChatImageFiles', () => {
  it('keeps supported images within the remaining attachment slots', () => {
    const one = png('one.png')
    const two = new File(['jpeg'], 'two.jpg', { type: 'image/jpeg' })
    const unsupported = new File(['txt'], 'note.txt', { type: 'text/plain' })

    const result = selectChatImageFiles(
      [one, unsupported, two],
      1,
    )

    expect(result.accepted).toEqual([one])
    expect(result.unsupportedCount).toBe(1)
    expect(result.overflowCount).toBe(1)
    expect(result.full).toBe(false)
  })

  it('reports a full attachment list without accepting files', () => {
    const result = selectChatImageFiles([png('one.png')], 0)

    expect(result).toEqual({
      accepted: [],
      unsupportedCount: 0,
      overflowCount: 1,
      full: true,
    })
  })
})

describe('ChatImageDropZone', () => {
  it('shows the receiving state and submits the selected image', () => {
    const file = png('product.png')
    const { onSelection, zone } = renderDropZone()

    fireEvent.dragEnter(zone, { dataTransfer: fileTransfer([file]) })
    expect(screen.getByText('松开即可上传图片')).toBeTruthy()
    expect(screen.getByText('支持 PNG、JPG、WebP · 还可添加 2 张')).toBeTruthy()

    fireEvent.drop(zone, { dataTransfer: fileTransfer([file]) })
    expect(onSelection).toHaveBeenCalledWith({
      accepted: [file],
      unsupportedCount: 0,
      overflowCount: 0,
      full: false,
    })
    expect(screen.queryByText('松开即可上传图片')).toBeNull()
  })

  it('keeps the overlay while leaving only a nested child', () => {
    const file = png('one.png')
    const { zone } = renderDropZone()
    const child = screen.getByTestId('composer-child')

    fireEvent.dragEnter(zone, { dataTransfer: fileTransfer([file]) })
    fireEvent.dragEnter(child, { dataTransfer: fileTransfer([file]) })
    fireEvent.dragLeave(child, { dataTransfer: fileTransfer([file]) })
    expect(screen.getByText('松开即可上传图片')).toBeTruthy()

    fireEvent.dragLeave(zone, { dataTransfer: fileTransfer([file]) })
    expect(screen.queryByText('松开即可上传图片')).toBeNull()
  })

  it('ignores a non-file drag', () => {
    const { onSelection, zone } = renderDropZone()

    fireEvent.dragEnter(zone, {
      dataTransfer: { files: [], types: ['text/plain'] },
    })
    fireEvent.drop(zone, {
      dataTransfer: { files: [], types: ['text/plain'] },
    })

    expect(screen.queryByText('松开即可上传图片')).toBeNull()
    expect(onSelection).not.toHaveBeenCalled()
  })

  it('ignores image drops while disabled', () => {
    const file = png('one.png')
    const { onSelection, zone } = renderDropZone({ disabled: true })

    fireEvent.dragEnter(zone, { dataTransfer: fileTransfer([file]) })
    fireEvent.drop(zone, { dataTransfer: fileTransfer([file]) })

    expect(screen.queryByText('松开即可上传图片')).toBeNull()
    expect(onSelection).not.toHaveBeenCalled()
  })

  it('reports a full list without showing the receiving overlay', () => {
    const file = png('one.png')
    const { onSelection, zone } = renderDropZone({ remainingSlots: 0 })

    fireEvent.dragEnter(zone, { dataTransfer: fileTransfer([file]) })
    expect(screen.queryByText('松开即可上传图片')).toBeNull()

    fireEvent.drop(zone, { dataTransfer: fileTransfer([file]) })
    expect(onSelection).toHaveBeenCalledWith({
      accepted: [],
      unsupportedCount: 0,
      overflowCount: 1,
      full: true,
    })
  })
})
