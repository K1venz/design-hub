import { useEffect, useMemo, useState } from 'react'
import { Link, Navigate, useLocation, type Location } from 'react-router-dom'
import { CheckCircle2Icon, TriangleAlertIcon } from 'lucide-react'

import {
  RegistrationVerificationError,
  useRegister,
  useResendRegistration,
  useVerifyRegistration,
} from '@/api/auth'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/stores/auth-store'

const MIN_PASSWORD = 8
const RESEND_DELAY_SECONDS = 60

type Step = 'details' | 'verification'
type PendingRegistration = {
  email: string
  challengeId: string
}

function passwordStrength(password: string): 0 | 1 | 2 | 3 {
  if (!password) return 0
  let variety = 0
  if (/[a-z]/.test(password)) variety++
  if (/[A-Z]/.test(password)) variety++
  if (/\d/.test(password)) variety++
  if (/[^a-zA-Z0-9]/.test(password)) variety++
  if (password.length < MIN_PASSWORD) return 1
  if (password.length >= 12 && variety >= 3) return 3
  if (variety >= 2) return 2
  return 1
}

const STRENGTH_META = [
  { label: '', tone: '', bars: 0 },
  { label: '弱', tone: 'bg-red-500', bars: 1 },
  { label: '中', tone: 'bg-amber-500', bars: 2 },
  { label: '强', tone: 'bg-emerald-500', bars: 3 },
] as const

function backTo(location: Location): string {
  const from = (location.state as { from?: Location } | null)?.from
  if (from?.pathname) return `${from.pathname}${from.search ?? ''}`
  return '/home'
}

function maskEmail(email: string): string {
  const [local, domain] = email.split('@')
  if (!local || !domain) return email
  if (local.length === 1) return `*${'@'}${domain}`
  return `${local[0]}***${local.at(-1)}@${domain}`
}

function RegistrationProgress({ step }: { step: Step }) {
  const verifying = step === 'verification'
  return (
    <ol aria-label="注册进度" className="grid grid-cols-2 gap-2 text-xs">
      <li
        aria-current={verifying ? undefined : 'step'}
        className={cn(
          'border-b pb-2 font-medium',
          verifying ? 'border-primary/35 text-muted-foreground' : 'border-primary text-foreground',
        )}
      >
        <span className="mr-1.5 font-mono text-[11px]">01</span>填写资料
      </li>
      <li
        aria-current={verifying ? 'step' : undefined}
        className={cn(
          'border-b pb-2 font-medium',
          verifying ? 'border-primary text-foreground' : 'border-border text-muted-foreground',
        )}
      >
        <span className="mr-1.5 font-mono text-[11px]">02</span>验证邮箱
      </li>
    </ol>
  )
}

export function RegisterPage() {
  const token = useAuthStore((state) => state.token)
  const location = useLocation()
  const register = useRegister()
  const verify = useVerifyRegistration()
  const resend = useResendRegistration()

  const [step, setStep] = useState<Step>('details')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [agreed, setAgreed] = useState(false)
  const [pendingRegistration, setPendingRegistration] = useState<PendingRegistration | null>(null)
  const [code, setCode] = useState('')
  const [resendAfter, setResendAfter] = useState(0)
  const [resendDeadline, setResendDeadline] = useState<number | null>(null)
  const [detailsError, setDetailsError] = useState<string | null>(null)
  const [verificationError, setVerificationError] = useState<string | null>(null)
  const [resendError, setResendError] = useState<string | null>(null)

  const strength = useMemo(() => passwordStrength(password), [password])
  const pwTooShort = password.length > 0 && password.length < MIN_PASSWORD
  const mismatch = confirm.length > 0 && confirm !== password
  const canRegister = Boolean(
    email.trim() && password.length >= MIN_PASSWORD && confirm === password && agreed,
  )
  const canVerify = /^\d{6}$/.test(code)
  const dest = backTo(location)
  const prefill = (location.state as { prefill?: unknown } | null)?.prefill
  const fromState = (location.state as { from?: Location } | null)?.from?.state ?? null
  const navState = prefill ? { prefill } : fromState

  useEffect(() => {
    if (step !== 'verification' || resendDeadline === null) return
    const timer = window.setInterval(() => {
      const seconds = Math.max(0, Math.ceil((resendDeadline - Date.now()) / 1_000))
      setResendAfter(seconds)
      if (seconds === 0) window.clearInterval(timer)
    }, 1_000)
    return () => window.clearInterval(timer)
  }, [resendDeadline, step])

  if (token) return <Navigate to={dest} replace state={navState} />

  async function submitDetails() {
    if (!canRegister) return
    const normalizedEmail = email.trim().toLowerCase()
    const finalName = name.trim() || normalizedEmail.split('@')[0] || '用户'
    setDetailsError(null)
    try {
      const acknowledgement = await register.mutateAsync({
        email: normalizedEmail,
        name: finalName,
        password,
      })
      setName('')
      setEmail('')
      setAgreed(false)
      setPendingRegistration({
        email: normalizedEmail,
        challengeId: acknowledgement.challenge_id,
      })
      setCode('')
      setVerificationError(null)
      setResendError(null)
      startResendCountdown()
      setStep('verification')
    } catch (error) {
      setDetailsError(error instanceof Error ? error.message : '注册暂时无法完成，请稍后重试。')
    } finally {
      setPassword('')
      setConfirm('')
      register.reset()
    }
  }

  async function submitVerification() {
    if (!canVerify || !pendingRegistration) return
    setVerificationError(null)
    try {
      await verify.mutateAsync({
        email: pendingRegistration.email,
        challengeId: pendingRegistration.challengeId,
        code,
      })
    } catch (error) {
      if (error instanceof RegistrationVerificationError && error.status === 400) {
        setVerificationError('验证码无效或已过期。请重新输入，或重新发送验证码。')
      } else if (error instanceof RegistrationVerificationError && error.status === 429) {
        setVerificationError(error.message)
      } else if (error instanceof Error && !(error instanceof RegistrationVerificationError)) {
        setVerificationError(error.message)
      } else {
        setVerificationError('验证码验证暂时无法完成，请稍后重试。')
      }
    } finally {
      setCode('')
      verify.reset()
    }
  }

  async function resendCode() {
    if (!pendingRegistration || resendAfter > 0) return
    setVerificationError(null)
    setResendError(null)
    try {
      const acknowledgement = await resend.mutateAsync({
        email: pendingRegistration.email,
        challengeId: pendingRegistration.challengeId,
      })
      setPendingRegistration((current) =>
        current?.challengeId === pendingRegistration.challengeId
          ? { ...current, challengeId: acknowledgement.challenge_id }
          : current,
      )
      startResendCountdown()
    } catch {
      setResendError('验证码暂时无法发送。请稍后重试，或返回修改资料。')
    } finally {
      resend.reset()
    }
  }

  function startResendCountdown() {
    setResendAfter(RESEND_DELAY_SECONDS)
    setResendDeadline(Date.now() + RESEND_DELAY_SECONDS * 1_000)
  }

  function returnToDetails() {
    if (!pendingRegistration) return
    setEmail(pendingRegistration.email)
    setPendingRegistration(null)
    setCode('')
    setVerificationError(null)
    setResendError(null)
    setResendAfter(0)
    setResendDeadline(null)
    setStep('details')
  }

  return (
    <AuthLayout>
      <RegistrationProgress step={step} />

      {step === 'details' && (
        <>
          <div className="space-y-2">
            <h2 className="pt-2 text-2xl font-semibold tracking-tight text-foreground">创建账号</h2>
            <p className="text-sm text-muted-foreground">填写资料后，我们会向你的邮箱发送验证码。</p>
          </div>

          {detailsError && (
            <div role="alert" className="border-destructive/30 bg-destructive/8 text-destructive flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm">
              <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
              <span>{detailsError}</span>
            </div>
          )}

          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              void submitDetails()
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="reg-name">昵称（选填）</Label>
              <Input id="reg-name" value={name} onChange={(event) => setName(event.target.value)} placeholder="怎么称呼你？" autoFocus />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-email">邮箱</Label>
              <Input id="reg-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-password">密码</Label>
              <Input id="reg-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={`至少 ${MIN_PASSWORD} 位`} aria-invalid={pwTooShort} />
              {password.length > 0 && (
                <div className="flex items-center gap-2 pt-0.5">
                  <div className="flex flex-1 gap-1" aria-label={`密码强度：${STRENGTH_META[strength].label || '未评估'}`}>
                    {[1, 2, 3].map((index) => (
                      <span key={index} className={cn('h-1 flex-1 rounded-full transition-colors motion-reduce:transition-none', index <= STRENGTH_META[strength].bars ? STRENGTH_META[strength].tone : 'bg-border')} />
                    ))}
                  </div>
                  <span className="text-muted-foreground w-6 text-xs">{STRENGTH_META[strength].label}</span>
                </div>
              )}
              {pwTooShort && <p className="text-destructive text-xs">密码至少 {MIN_PASSWORD} 位</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="reg-confirm">确认密码</Label>
              <Input id="reg-confirm" type="password" autoComplete="new-password" value={confirm} onChange={(event) => setConfirm(event.target.value)} placeholder="再输入一次密码" aria-invalid={mismatch} />
              {mismatch && <p className="text-destructive text-xs">两次密码不一致</p>}
            </div>

            <label className="text-muted-foreground flex cursor-pointer items-start gap-2 text-xs leading-relaxed">
              <Checkbox className="mt-0.5" checked={agreed} onChange={(event) => setAgreed(event.target.checked)} />
              <span>
                我已阅读并同意
                <Link className="text-primary hover:underline" to="/terms" target="_blank" rel="noreferrer">《用户协议》</Link>
                和
                <Link className="text-primary hover:underline" to="/privacy" target="_blank" rel="noreferrer">《隐私政策》</Link>
              </span>
            </label>

            <Button type="submit" size="lg" className="h-11 w-full" disabled={!canRegister || register.isPending}>
              {register.isPending ? '发送中…' : '发送验证码'}
            </Button>
          </form>
        </>
      )}

      {step === 'verification' && (
        <>
          <div className="space-y-2">
            <h2 className="pt-2 text-2xl font-semibold tracking-tight text-foreground">验证邮箱</h2>
            <p className="text-sm text-muted-foreground">验证码已发送至 <span className="font-medium text-foreground">{maskEmail(pendingRegistration!.email)}</span>。</p>
          </div>

          {(verificationError || resendError) && (
            <div id={verificationError ? 'reg-verification-error' : undefined} role="alert" className="border-destructive/30 bg-destructive/8 text-destructive flex items-start gap-2 rounded-lg border px-3 py-2.5 text-sm">
              <TriangleAlertIcon className="mt-0.5 size-4 shrink-0" />
              <span>{verificationError ?? resendError}</span>
            </div>
          )}

          <form
            className="space-y-4"
            onSubmit={(event) => {
              event.preventDefault()
              void submitVerification()
            }}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <Label htmlFor="reg-code">验证码</Label>
                <button type="button" className="text-muted-foreground hover:text-foreground text-xs transition-colors motion-reduce:transition-none hover:underline disabled:cursor-not-allowed disabled:opacity-50" disabled={resendAfter > 0 || resend.isPending} onClick={() => void resendCode()}>
                  {resend.isPending ? '发送中…' : resendAfter > 0 ? `${resendAfter} 秒后可重新发送` : '重新发送验证码'}
                </button>
              </div>
              <Input id="reg-code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={6} value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))} placeholder="输入 6 位数字" autoFocus aria-invalid={Boolean(verificationError)} aria-describedby={verificationError ? 'reg-verification-error' : undefined} />
              <p className="text-muted-foreground text-xs">仅输入邮件中的 6 位数字验证码。</p>
            </div>
            <Button type="submit" size="lg" className="h-11 w-full" disabled={!canVerify || verify.isPending}>
              {verify.isPending ? '验证中…' : '验证并进入 Design Hub'}
            </Button>
          </form>

          <div className="border-border/70 flex items-start gap-2 border-t pt-4 text-sm">
            <CheckCircle2Icon className="text-primary mt-0.5 size-4 shrink-0" aria-hidden="true" />
            <div className="space-y-1">
              <p className="text-foreground">验证成功后会自动进入 Design Hub。</p>
              <button type="button" className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-4" onClick={returnToDetails}>返回修改资料</button>
            </div>
          </div>
        </>
      )}

      <p className="text-center text-sm text-muted-foreground">
        已有账号？
        <Link to="/login" state={location.state} className="text-primary ml-1 font-medium hover:underline">去登录</Link>
      </p>
    </AuthLayout>
  )
}
