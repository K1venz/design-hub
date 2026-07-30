import { describe, expect, it } from 'vitest'

import {
  PRIMARY_NAV_ITEMS,
  getAccountNavItems,
} from './navigation'

describe('global navigation contract', () => {
  it('exposes the approved product destinations in order', () => {
    expect(PRIMARY_NAV_ITEMS.map(({ label, to }) => ({ label, to }))).toEqual([
      { label: '首页', to: '/home' },
      { label: '帮我设计', to: '/chat' },
      { label: '商品套图', to: '/set' },
      { label: '爆款复刻', to: '/clone' },
      { label: '换背景', to: '/background' },
      { label: '历史', to: '/history' },
    ])
  })

  it('exposes management destinations only to managers', () => {
    expect(getAccountNavItems('设计师')).toEqual([])
    expect(getAccountNavItems('管理者').map(({ label, to }) => ({ label, to }))).toEqual([
      { label: '管理后台', to: '/admin' },
    ])
  })
})
