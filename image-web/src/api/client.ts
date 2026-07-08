import createClient, { type Middleware } from 'openapi-fetch'

import type { paths } from '@/api/schema'
import { useAuthStore } from '@/stores/auth-store'

/** 401 事件：令牌失效/过期时广播，App 顶层据此跳登录并提示。 */
export const UNAUTHORIZED_EVENT = 'auth:unauthorized'

const PUBLIC_PATHS = ['/auth/']

function isPublic(url: string): boolean {
  return PUBLIC_PATHS.some((p) => url.includes(p))
}

const authMiddleware: Middleware = {
  onRequest({ request }) {
    const { token } = useAuthStore.getState()
    if (token && !isPublic(request.url)) {
      request.headers.set('Authorization', `Bearer ${token}`)
    }
    return request
  },
  onResponse({ request, response }) {
    // 滑动续期（ISSUE-0058）：受保护响应带 X-Renewed-Token（后端在令牌过半衰期时续签）→
    // 无感换令牌，经 rememberAwareStorage 落原存储位（记住我模式不升级不降级）。
    const renewed = response.headers.get('X-Renewed-Token')
    if (renewed) useAuthStore.getState().setToken(renewed)

    // 受保护端点返回 401 => 令牌失效：清会话并广播，由顶层跳登录。
    // 登录端点(/auth/*)的 401 是「授权 code 无效」，交给登录表单处理，不清会话。
    if (response.status === 401 && !isPublic(request.url)) {
      useAuthStore.getState().clear()
      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))
      }
    }
    return response
  },
}

/**
 * 类型化契约客户端：baseUrl `/api` 经 Vite dev proxy 转发到后端（绕过 CORS）。
 * 唯一契约源 = `src/api/schema.d.ts`（由后端 OpenAPI 生成，见 `npm run gen:api`）。
 */
export const api = createClient<paths>({ baseUrl: '/api' })
api.use(authMiddleware)
