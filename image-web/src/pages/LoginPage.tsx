import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, type Location } from 'react-router-dom'
import { TriangleAlertIcon } from 'lucide-react'

import { useLogin } from '@/api/auth'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthStore } from '@/stores/auth-store'

/** 登录墙回跳目标：ProtectedRoute 存进 state.from 的原始 location（含 query）。 */
function backTo(location: Location): string {
  const from = (location.state as { from?: Location } | null)?.from
  if (from?.pathname) return `${from.pathname}${from.search ?? ''}`
  return '/'
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
  if (token) return <Navigate to={dest} replace />

  async function submit() {
    try {
      await login.mutateAsync({ email: email.trim(), password })
      navigate(dest, { replace: true })
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
          <span
            className="text-muted-foreground/70 cursor-not-allowed text-sm"
            title="找回密码即将上线"
          >
            忘记密码？
          </span>
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
