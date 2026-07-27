import { describe, expect, it } from 'vitest'

import { TOOL_TILES } from './home'

describe('home pricing copy', () => {
  it('shows the fixed ordinary image price', () => {
    expect(TOOL_TILES.find((tile) => tile.key === 'single')?.desc).toBe(
      '只出一张 · ¥0.05',
    )
  })
})
