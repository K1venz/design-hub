// @vitest-environment jsdom

import { createElement, type ComponentProps } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'

import { ChatComposer } from '@/components/chat/ChatComposer'
import type { ChatImageFileSelection } from '@/components/chat/ChatImageDropZone'
import type { ModelSelection } from '@/components/models/model-selection'

function selection(modelId: string): ModelSelection {
  return {
    modelId,
    models: [
      {
        id: modelId,
        display_name: modelId,
        is_default: true,
        ...(modelId === 'doubao-chat'
          ? {}
          : {
              image_capabilities: {
                max_count: 7,
                supports_references: true,
                render_tiers: [
                  {
                    id: 'standard' as const,
                    label: '1K 标准',
                    ratios: ['1:1', '4:5'],
                  },
                ],
              },
            }),
      },
    ],
    state: 'ready',
    select: vi.fn(),
    retry: vi.fn(),
  }
}

type ComposerProps = ComponentProps<typeof ChatComposer> & {
  onFileSelection: (selection: ChatImageFileSelection) => void
}

function composerProps(overrides: Partial<ComposerProps> = {}): ComposerProps {
  return {
    draft: '生成商品海报',
    onDraftChange: vi.fn(),
    attached: [],
    selectedEditSource: null,
    token: null,
    busy: false,
    modelsReady: true,
    uploadPending: false,
    imageOptions: {
      renderTier: 'standard',
      count: 1,
      ratio: '1:1',
    },
    onImageOptionsChange: vi.fn(),
    chatSelection: selection('doubao-chat'),
    imageSelection: selection('gpt-image-2'),
    onPickFiles: vi.fn(),
    onFileSelection: vi.fn(),
    onRemoveAttachment: vi.fn(),
    onCancelEdit: vi.fn(),
    onReversePrompt: vi.fn(),
    onClear: vi.fn(),
    onSend: vi.fn(),
    ...overrides,
  }
}

afterEach(cleanup)

it('does not send with Enter while an image upload is pending', () => {
  const onSend = vi.fn()
  render(
    createElement(
      ChatComposer,
      composerProps({ uploadPending: true, onSend }),
    ),
  )

  fireEvent.keyDown(screen.getByLabelText('图片创作提示词'), {
    key: 'Enter',
    shiftKey: false,
  })

  expect(onSend).not.toHaveBeenCalled()
})

it('forwards a dropped image through the unified file selection action', () => {
  const onPickFiles = vi.fn()
  const onFileSelection = vi.fn()
  const { container } = render(
    createElement(
      ChatComposer,
      composerProps({ onPickFiles, onFileSelection }),
    ),
  )
  const zone = container.querySelector('[data-chat-image-drop-zone]')
  if (!zone) throw new Error('drop zone was not rendered')
  const file = new File(['png'], 'product.png', { type: 'image/png' })

  fireEvent.drop(zone, {
    dataTransfer: { types: ['Files'], files: [file] },
  })

  expect(onPickFiles).toHaveBeenCalledWith([file])
  expect(onFileSelection).toHaveBeenCalledWith({
    accepted: [file],
    unsupportedCount: 0,
    overflowCount: 0,
    full: false,
  })
})
