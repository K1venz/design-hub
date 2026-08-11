import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { CheckCircle2Icon, TriangleAlertIcon } from 'lucide-react'

import { useForgotPassword, useResetPassword } from '@/api/auth'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

const MIN_PASSWORD = 8

type Step = 'email' | 'reset' | 'done'

export function ForgotPasswordPage() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const location = useLocation()
  const seededEmail =
    (location.state as { email?: string } | null)?.email?.trim() ?? ''

  const forgot = useForgotPassword()
  const reset = useResetPassword()

  const [step, setStep] = useState<Step>('email')
  const [email, setEmail] = useState(seededEmail)
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [info, setInfo] = useState<string | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const mismatch = confirm.length > 0 && confirm !== password
  const pwTooShort = password.length > 0 && password.length < MIN_PASSWORD
  const codeOk = /^\d{6}$/.test(code.trim())
  const canReset =
    email.trim() && codeOk && password.length >= MIN_PASSWORD && confirm === password

  if (token) return <Navigate to="/home" replace />

  async function sendCode() {
    const target = email.trim()
    if (!target) return
    setInfo(null)
    setErrorMessage(null)
    forgot.reset()
    reset.reset()
    try {
      const data = await forgot.mutateAsync({ email: target })
      setInfo(data.message)
      setCode('')
      setStep('reset')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '验证码暂时无法发送，请稍后重试。')
    } finally {
      forgot.reset()
    }
  }

  async function submitReset() {
    if (!canReset) return
    setInfo(null)
    setErrorMessage(null)
    forgot.reset()
    reset.reset()
    try {
      await reset.mutateAsync({
        email: email.trim(),
        code: code.trim(),
        password,
      })
      setStep('done')
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : '密码暂时无法重置，请稍后重试。')
    } finally {
      setCode('')
      setPassword('')
      setConfirm('')
      reset.reset()
    }
  }

  return (
    <AuthLayout>
      <div className="space-y-2">
        <h2 className="pt-2 text-2xl font-semibold tracking-tight text-foreground">找回密码</h2>
        <p className="text-sm text-muted-foreground">
          {step === 'email' && '输入注册邮箱，我们会发送 6 位验证码。'}
          {step === 'reset' && '输入邮箱收到的验证码，并设置新密码。'}
          {step === 'done' && '密码已更新，请使用新密码登录。'}
        </p>
      </div>

      {errorMessage && (
        <div
          role="alert"
          className="border-destructive/30 bg-destructive/8 text-destructive flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm"
        >
          <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {info && step !== 'done' && (
        <div className="border-wb-brand/25 bg-wb-tint-1 text-wb-ink-3 flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm">
          <span>{info}</span>
        </div>
      )}

      {step === 'email' && (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void sendCode()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="forgot-email">邮箱</Label>
            <Input
              id="forgot-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoFocus
            />
          </div>
          <Button
            type="submit"
            size="lg"
            className="h-11 w-full"
            disabled={!email.trim() || forgot.isPending}
          >
            {forgot.isPending ? '发送中…' : '发送验证码'}
          </Button>
        </form>
      )}

      {step === 'reset' && (
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault()
            void submitReset()
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="reset-email">邮箱</Label>
            <Input
              id="reset-email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="reset-code">验证码</Label>
              <button
                type="button"
                className="text-muted-foreground hover:text-foreground text-xs transition-colors hover:underline disabled:opacity-50"
                disabled={forgot.isPending || !email.trim()}
                onClick={() => void sendCode()}
              >
                {forgot.isPending ? '发送中…' : '重新发送'}
              </button>
            </div>
            <Input
              id="reset-code"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              placeholder="6 位数字"
              autoFocus
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="reset-password">新密码</Label>
            <Input
              id="reset-password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={`至少 ${MIN_PASSWORD} 位`}
            />
            {pwTooShort && (
              <p className="text-destructive text-xs">密码至少 {MIN_PASSWORD} 位</p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="reset-confirm">确认新密码</Label>
            <Input
              id="reset-confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="再输入一次"
              className={cn(mismatch && 'border-destructive')}
            />
            {mismatch && <p className="text-destructive text-xs">两次密码不一致</p>}
          </div>
          <Button
            type="submit"
            size="lg"
            className="h-11 w-full"
            disabled={!canReset || reset.isPending}
          >
            {reset.isPending ? '提交中…' : '重置密码'}
          </Button>
        </form>
      )}

      {step === 'done' && (
        <div className="space-y-5">
          <div className="bg-emerald-500/8 text-emerald-700 flex items-start gap-2 rounded-lg border border-emerald-500/25 px-3 py-3 text-sm">
            <CheckCircle2Icon className="mt-0.5 size-4 shrink-0" />
            <span>密码已重置成功。请返回登录页，使用新密码登录。</span>
          </div>
          <Button
            size="lg"
            className="h-11 w-full"
            onClick={() =>
              navigate('/login', {
                replace: true,
                state: { email: email.trim() },
              })
            }
          >
            去登录
          </Button>
        </div>
      )}

      <p className="text-center text-sm text-muted-foreground">
        想起密码了？
        <Link
          to="/login"
          state={email.trim() ? { email: email.trim() } : undefined}
          className="text-primary ml-1 font-medium hover:underline"
        >
          返回登录
        </Link>
      </p>
    </AuthLayout>
  )
}
