import { useMemo, useState } from 'react'
import { Link, Navigate, useLocation, useNavigate, type Location } from 'react-router-dom'
import { TriangleAlertIcon } from 'lucide-react'

import { useRegister } from '@/api/auth'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

const MIN_PASSWORD = 8

/** 密码强度：0 无 / 1 弱 / 2 中 / 3 强。基于长度 + 字符种类。 */
function passwordStrength(pw: string): 0 | 1 | 2 | 3 {
  if (!pw) return 0
  let variety = 0
  if (/[a-z]/.test(pw)) variety++
  if (/[A-Z]/.test(pw)) variety++
  if (/\d/.test(pw)) variety++
  if (/[^a-zA-Z0-9]/.test(pw)) variety++
  if (pw.length < MIN_PASSWORD) return 1
  if (pw.length >= 12 && variety >= 3) return 3
  if (variety >= 2) return 2
  return 1
}

const STRENGTH_META = [
  { label: '', tone: '', bars: 0 },
  { label: '弱', tone: 'bg-red-500', bars: 1 },
  { label: '中', tone: 'bg-amber-500', bars: 2 },
  { label: '强', tone: 'bg-emerald-500', bars: 3 },
] as const

/** 登录墙回跳目标（与登录页同源）。 */
function backTo(location: Location): string {
  const from = (location.state as { from?: Location } | null)?.from
  if (from?.pathname) return `${from.pathname}${from.search ?? ''}`
  return '/'
}

export function RegisterPage() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const location = useLocation()
  const register = useRegister()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [agreed, setAgreed] = useState(false)

  const strength = useMemo(() => passwordStrength(password), [password])
  const pwTooShort = password.length > 0 && password.length < MIN_PASSWORD
  const mismatch = confirm.length > 0 && confirm !== password
  const valid =
    email.trim() && password.length >= MIN_PASSWORD && confirm === password && agreed

  const dest = backTo(location)
  // 「做同款」携配方过登录墙转注册：注册后转发 prefill 随行到目标页（WorkbenchPage 消费）。
  // 否则恢复受保护路由原 state（如 chat 首句 q），使 Hero→登录墙→自动发首条不丢。
  const prefill = (location.state as { prefill?: unknown } | null)?.prefill
  const fromState = (location.state as { from?: Location } | null)?.from?.state ?? null
  const navState = prefill ? { prefill } : fromState
  if (token) return <Navigate to={dest} replace state={navState} />

  async function submit() {
    if (!valid) return
    try {
      // 昵称选填：留空则用邮箱前缀兜底（后端仍需一个 name）
      const finalName = name.trim() || email.trim().split('@')[0] || '用户'
      await register.mutateAsync({ email: email.trim(), name: finalName, password })
      navigate(dest, { replace: true, state: navState })
    } catch {
      // 错误经 register.error 呈现
    }
  }

  return (
    <AuthLayout>
      <div className="space-y-2">
        <h2 className="pt-2 text-2xl font-semibold tracking-tight text-foreground">注册账号</h2>
        <p className="text-sm text-muted-foreground">注册即可使用，上传产品图就能出图。</p>
      </div>

      {register.isError && (
        <div className="border-destructive/30 bg-destructive/8 text-destructive flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm">
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
          <span>{register.error.message}</span>
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
          <Label htmlFor="reg-name">
            昵称 <span className="text-muted-foreground font-normal">（选填）</span>
          </Label>
          <Input
            id="reg-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="怎么称呼你"
            autoFocus
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="reg-email">邮箱</Label>
          <Input
            id="reg-email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@company.com"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="reg-password">密码</Label>
          <Input
            id="reg-password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={`至少 ${MIN_PASSWORD} 位`}
            aria-invalid={pwTooShort}
          />
          {password.length > 0 && (
            <div className="flex items-center gap-2 pt-0.5">
              <div className="flex flex-1 gap-1">
                {[1, 2, 3].map((i) => (
                  <span
                    key={i}
                    className={cn(
                      'h-1 flex-1 rounded-full transition-colors',
                      i <= STRENGTH_META[strength].bars
                        ? STRENGTH_META[strength].tone
                        : 'bg-border',
                    )}
                  />
                ))}
              </div>
              <span className="text-muted-foreground w-6 text-xs">
                {STRENGTH_META[strength].label}
              </span>
            </div>
          )}
          {pwTooShort && <p className="text-destructive text-xs">密码至少 {MIN_PASSWORD} 位</p>}
        </div>
        <div className="space-y-2">
          <Label htmlFor="reg-confirm">确认密码</Label>
          <Input
            id="reg-confirm"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="再输一次密码"
            aria-invalid={mismatch}
          />
          {mismatch && <p className="text-destructive text-xs">两次密码不一致</p>}
        </div>

        <label className="text-muted-foreground flex cursor-pointer items-start gap-2 text-xs leading-relaxed">
          <Checkbox
            className="mt-0.5"
            checked={agreed}
            onChange={(e) => setAgreed(e.target.checked)}
          />
          <span>
            我已阅读并同意
            <Link className="text-primary hover:underline" to="/terms" target="_blank" rel="noreferrer">《用户协议》</Link>
            与
            <Link className="text-primary hover:underline" to="/privacy" target="_blank" rel="noreferrer">《隐私政策》</Link>
          </span>
        </label>

        <Button
          type="submit"
          size="lg"
          className="h-11 w-full"
          disabled={!valid || register.isPending}
        >
          {register.isPending ? '注册中…' : '注册并进入'}
        </Button>
      </form>

      <p className="text-center text-sm text-muted-foreground">
        已有账号？
        <Link to="/login" state={location.state} className="text-primary ml-1 font-medium hover:underline">
          去登录
        </Link>
      </p>
    </AuthLayout>
  )
}
