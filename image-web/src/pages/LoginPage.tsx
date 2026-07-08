import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, type Location } from 'react-router-dom'
import { TriangleAlertIcon } from 'lucide-react'

import { useLogin } from '@/api/auth'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { setAuthPersistent } from '@/stores/auth-storage'
import { useAuthStore } from '@/stores/auth-store'

/**
 * 内测期占位：管理员联系方式。用户尚未拍板是否公开具体邮箱/微信——
 * 先留空，弹窗只提示「联系管理员协助」；用户给了填此常量即自动显示。
 */
const ADMIN_CONTACT = ''

/** 忘记密码占位弹窗（内测期无自助找回，引导联系管理员）。 */
function ForgotPasswordDialog() {
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          className="text-muted-foreground/80 hover:text-foreground text-sm transition-colors hover:underline"
        >
          忘记密码？
        </button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>找回密码</DialogTitle>
          <DialogDescription>
            内测期间暂未开放自助找回密码。如需重置，请联系管理员协助。
          </DialogDescription>
        </DialogHeader>
        {ADMIN_CONTACT ? (
          <p className="text-foreground text-sm">联系方式：{ADMIN_CONTACT}</p>
        ) : null}
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">知道了</Button>
          </DialogClose>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 登录墙回跳目标：ProtectedRoute 存进 state.from 的原始 location（含 query）。
 *  无 from 默认落 /home 工作首页（`/` 已是营销 Hero 落地页，ISSUE-0061）。 */
function backTo(location: Location): string {
  const from = (location.state as { from?: Location } | null)?.from
  if (from?.pathname) return `${from.pathname}${from.search ?? ''}`
  return '/home'
}

export function LoginPage() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const location = useLocation()
  const login = useLogin()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)

  const dest = backTo(location)
  // 「做同款」等入口携配方过登录墙：登录后转发 prefill 随行到目标页（WorkbenchPage 消费）。
  // 否则恢复受保护路由原 state（如 chat 首句 q），使 Hero→登录墙→自动发首条不丢。
  const prefill = (location.state as { prefill?: unknown } | null)?.prefill
  const fromState = (location.state as { from?: Location } | null)?.from?.state ?? null
  const navState = prefill ? { prefill } : fromState
  if (token) return <Navigate to={dest} replace state={navState} />

  async function submit() {
    setAuthPersistent(remember) // 决定 token 落 localStorage(持久) 还是 sessionStorage(仅会话)
    try {
      await login.mutateAsync({ email: email.trim(), password })
      navigate(dest, { replace: true, state: navState })
    } catch {
      // 错误经 login.error 呈现
    }
  }

  return (
    <AuthLayout>
      <div className="space-y-2">
        <h2 className="pt-2 text-2xl font-semibold tracking-tight text-foreground">登录实朴</h2>
        <p className="text-sm text-muted-foreground">用邮箱和密码登录。</p>
      </div>

      {login.isError && (
        <div className="border-destructive/30 bg-destructive/8 text-destructive flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm">
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
          <span>{login.error.message}</span>
        </div>
      )}

      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault()
          void submit()
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="login-email">邮箱</Label>
          <Input
            id="login-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="login-password">密码</Label>
          <Input
            id="login-password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="••••••••"
          />
        </div>
        <div className="flex items-center justify-between">
          <label className="text-muted-foreground flex cursor-pointer items-center gap-2 text-sm">
            <Checkbox checked={remember} onChange={(e) => setRemember(e.target.checked)} />
            记住我
          </label>
          <ForgotPasswordDialog />
        </div>
        <Button
          type="submit"
          size="lg"
          className="h-11 w-full"
          disabled={!email.trim() || !password || login.isPending}
        >
          {login.isPending ? '登录中…' : '登录'}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        还没有账号？
        <Link to="/register" state={location.state} className="text-primary ml-1 font-medium hover:underline">
          去注册
        </Link>
      </p>
    </AuthLayout>
  )
}
