import { describe, expect, it } from 'vitest'

import { TOOL_TILES } from './home'

describe('home generation copy', () => {
  it('describes the tool without exposing a fixed image price', () => {
    expect(TOOL_TILES.find((tile) => tile.key === 'single')?.desc).toBe(
      '快速生成 1 张商品图',
    )
  })
})
