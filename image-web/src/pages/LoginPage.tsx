import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ArrowRightIcon, Loader2Icon, TriangleAlertIcon } from 'lucide-react'

import { useLogin } from '@/api/auth'
import { BrandMark, Wordmark } from '@/components/brand/Wordmark'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { ROLE_DESIGNER, ROLE_MANAGER, useAuthStore, type Role } from '@/stores/auth-store'

const PROVIDERS = [
  { key: 'feishu', label: '飞书' },
  { key: 'dingtalk', label: '钉钉' },
] as const

/** mock 后端按 code 前缀映射部门 → 角色（见 image-code MockOAuthClient）. */
function mockCode(provider: string, role: Role): string {
  return role === ROLE_MANAGER ? `mgr-${provider}-mock` : `${provider}-设计师-mock`
}

export function LoginPage() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const login = useLogin()
  const [role, setRole] = useState<Role>(ROLE_DESIGNER)
  const [pending, setPending] = useState<string | null>(null)

  // 已有会话直接进站
  if (token) return <Navigate to="/" replace />

  async function signIn(provider: string) {
    setPending(provider)
    try {
      await login.mutateAsync({ provider, code: mockCode(provider, role) })
      navigate('/', { replace: true })
    } catch {
      // 错误经 login.error 呈现
    } finally {
      setPending(null)
    }
  }

  return (
    <div className="grid min-h-svh lg:grid-cols-[1.05fr_1fr]">
      {/* 品牌面板（大屏）：青墨底 + 纸纹 + 叠帧意象 */}
      <aside className="bg-primary text-primary-foreground relative hidden overflow-hidden lg:flex lg:flex-col lg:justify-between lg:p-14">
        <div className="paper-grain pointer-events-none absolute inset-0 opacity-[0.12]" />
        <div
          className="animate-in fade-in slide-in-from-left-2 relative flex items-center gap-3 duration-700"
        >
          <BrandMark className="size-9" />
          <span className="font-display text-lg tracking-[0.16em]">STUDIO COPILOT</span>
        </div>

        <div className="animate-in fade-in slide-in-from-left-3 relative max-w-md space-y-5 duration-700">
          <h1 className="font-display text-[2.7rem] leading-[1.08] tracking-tight">
            设计师的
            <br />
            AI 副驾驶
          </h1>
          <p className="text-primary-foreground/72 text-[15px] leading-relaxed">
            产品图 → 高质量电商图。一单一档管理客户与项目，出图、选稿、改稿、交付一条线贯通。
          </p>
        </div>

        {/* 叠帧装饰：呼应「多候选 / 多轮次」 */}
        <div className="relative flex items-end justify-between">
          <span className="text-primary-foreground/55 font-mono text-xs">
            design_hub · 图生图引擎 v0.1
          </span>
          <div className="pointer-events-none absolute -right-6 -bottom-2 opacity-30">
            <div className="border-primary-foreground/40 size-24 rounded-xl border" />
            <div className="border-primary-foreground/55 absolute top-4 left-4 size-24 rounded-xl border" />
            <div className="bg-highlight absolute top-[3.4rem] left-[3.4rem] size-3 rounded-full" />
          </div>
        </div>
      </aside>

      {/* 登录表单（暖纸底） */}
      <main className="paper-grain flex items-center justify-center bg-background px-6 py-12">
        <div className="animate-in fade-in slide-in-from-bottom-2 w-full max-w-sm space-y-8 duration-500">
          <div className="space-y-2">
            <div className="lg:hidden">
              <Wordmark />
            </div>
            <h2 className="pt-2 text-2xl font-semibold tracking-tight text-foreground">
              登录设计中台
            </h2>
            <p className="text-sm text-muted-foreground">使用企业账号继续，登录即接受访问授权。</p>
          </div>

          {/* 开发态：选择 mock 身份以验证按角色导航（生产隐藏） */}
          {import.meta.env.DEV && (
            <div className="border-border/70 bg-muted/40 space-y-2 rounded-lg border border-dashed p-3">
              <p className="text-muted-foreground text-[11px] font-medium tracking-wide uppercase">
                开发 mock 身份
              </p>
              <div className="grid grid-cols-2 gap-1.5">
                {([ROLE_DESIGNER, ROLE_MANAGER] as Role[]).map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => setRole(r)}
                    className={cn(
                      'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                      role === r
                        ? 'bg-primary text-primary-foreground'
                        : 'text-muted-foreground hover:bg-background',
                    )}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          )}

          {login.isError && (
            <div className="border-destructive/30 bg-destructive/8 text-destructive flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm">
              <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
              <span>{login.error.message}</span>
            </div>
          )}

          <div className="space-y-2.5">
            {PROVIDERS.map((p) => {
              const busy = pending === p.key
              return (
                <Button
                  key={p.key}
                  variant="outline"
                  size="lg"
                  disabled={login.isPending}
                  onClick={() => signIn(p.key)}
                  className="group border-border/80 h-12 w-full justify-between bg-card text-[15px] font-medium hover:bg-card hover:border-primary/40"
                >
                  <span className="flex items-center gap-2.5">
                    <span className="bg-primary/10 text-primary flex size-6 items-center justify-center rounded-md text-xs font-semibold">
                      {p.label.slice(0, 1)}
                    </span>
                    {p.label}登录
                  </span>
                  {busy ? (
                    <Loader2Icon className="size-4 animate-spin" />
                  ) : (
                    <ArrowRightIcon className="text-muted-foreground size-4 transition-transform group-hover:translate-x-0.5" />
                  )}
                </Button>
              )
            })}
          </div>

          <p className="text-muted-foreground/80 text-center text-xs">
            登录遇到问题？请联系团队管理者开通访问权限。
          </p>
        </div>
      </main>
    </div>
  )
}
