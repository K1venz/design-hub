import { describe, expect, it } from 'vitest'

import { buildChatMessageBody } from '@/api/chat'

describe('buildChatMessageBody', () => {
  it('omits edit source for normal chat messages', () => {
    expect(
      buildChatMessageBody({
        sessionId: 's1',
        message: '做一张主图',
        uploadIds: ['u1'],
      }),
    ).toEqual({
      session_id: 's1',
      message: '做一张主图',
      upload_ids: ['u1'],
    })
  })

  it('maps a selected generated image to edit_source_image_key', () => {
    expect(
      buildChatMessageBody({
        sessionId: 's1',
        message: '背景换成海边',
        editSourceImageKey: 'result.png',
      }),
    ).toEqual({
      session_id: 's1',
      message: '背景换成海边',
      upload_ids: [],
      edit_source_image_key: 'result.png',
    })
  })
})
