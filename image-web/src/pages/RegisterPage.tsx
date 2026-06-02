import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { TriangleAlertIcon } from 'lucide-react'

import { useRegister } from '@/api/auth'
import { AuthLayout } from '@/components/auth/AuthLayout'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuthStore } from '@/stores/auth-store'

const MIN_PASSWORD = 8

export function RegisterPage() {
  const token = useAuthStore((s) => s.token)
  const navigate = useNavigate()
  const register = useRegister()
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [password, setPassword] = useState('')

  if (token) return <Navigate to="/" replace />

  const pwTooShort = password.length > 0 && password.length < MIN_PASSWORD
  const valid = email.trim() && name.trim() && password.length >= MIN_PASSWORD

  async function submit() {
    if (!valid) return
    try {
      await register.mutateAsync({ email: email.trim(), name: name.trim(), password })
      navigate('/', { replace: true })
    } catch {
      // 错误经 register.error 呈现
    }
  }

  return (
    <AuthLayout>
      <div className="space-y-2">
        <h2 className="pt-2 text-2xl font-semibold tracking-tight text-foreground">注册账号</h2>
        <p className="text-sm text-muted-foreground">注册即可使用，默认设计师角色。</p>
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
          <Label htmlFor="reg-name">姓名</Label>
          <Input
            id="reg-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="你的名字"
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
          {pwTooShort && <p className="text-destructive text-xs">密码至少 {MIN_PASSWORD} 位</p>}
        </div>
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
        <Link to="/login" className="text-primary ml-1 font-medium hover:underline">
          去登录
        </Link>
      </p>
    </AuthLayout>
  )
}
