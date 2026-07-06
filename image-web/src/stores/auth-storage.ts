import type { StateStorage } from 'zustand/middleware'

/**
 * 「记住我」存储路由——决定登录会话落在哪个 Web Storage：
 * - 勾选（默认）→ localStorage：关浏览器重开仍登录。
 * - 不勾 → sessionStorage：关浏览器/标签页即登出。
 *
 * 登录前由 LoginPage 调 {@link setAuthPersistent} 选定写入目标。读取时两处都看
 * （localStorage 优先），并据命中来源回填当前模式——故刷新/水合无需预先知道用户的
 * 「记住我」选择，且不会把「仅会话」态在刷新后误升级为持久态。
 */
let persistent = true

export function setAuthPersistent(value: boolean): void {
  persistent = value
}

export const rememberAwareStorage: StateStorage = {
  getItem: (name) => {
    const fromLocal = localStorage.getItem(name)
    if (fromLocal !== null) {
      persistent = true
      return fromLocal
    }
    const fromSession = sessionStorage.getItem(name)
    if (fromSession !== null) {
      persistent = false
      return fromSession
    }
    return null
  },
  setItem: (name, value) => {
    if (persistent) {
      localStorage.setItem(name, value)
      sessionStorage.removeItem(name)
    } else {
      sessionStorage.setItem(name, value)
      localStorage.removeItem(name)
    }
  },
  removeItem: (name) => {
    localStorage.removeItem(name)
    sessionStorage.removeItem(name)
  },
}
