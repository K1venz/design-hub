import type { components } from '@/api/schema'

/**
 * 过渡契约：自建邮箱密码认证的新端点类型（后端 ISSUE-0015 尚未落地）。
 * 后端就绪后 `npm run gen:api` 会把这些端点纳入生成的 schema.d.ts，
 * 届时**删除本文件**并把 client 的 `paths & AuthExtPaths` 改回 `paths`。
 * 形状对齐 spec docs/superpowers/specs/2026-06-02-自建邮箱密码认证-design.md §5。
 */
type Role = components['schemas']['Role']

export interface AppUserOut {
  id: number
  email: string
  name: string
  role: Role
  created_at: string
}

interface SessionResp {
  200: { content: { 'application/json': { jwt: string; role: Role; name: string } } }
}

type NoParams = { query?: never; header?: never; path?: never; cookie?: never }

export interface AuthExtPaths {
  '/auth/register': {
    post: {
      parameters: NoParams
      requestBody: {
        content: { 'application/json': { email: string; password: string; name: string } }
      }
      responses: SessionResp
    }
  }
  '/auth/login': {
    post: {
      parameters: NoParams
      requestBody: { content: { 'application/json': { email: string; password: string } } }
      responses: SessionResp
    }
  }
  '/admin/users': {
    get: {
      parameters: NoParams
      responses: { 200: { content: { 'application/json': AppUserOut[] } } }
    }
  }
  '/admin/users/{user_id}/role': {
    put: {
      parameters: { query?: never; header?: never; path: { user_id: number }; cookie?: never }
      requestBody: { content: { 'application/json': { role: Role } } }
      responses: { 200: { content: { 'application/json': AppUserOut } } }
    }
  }
}
