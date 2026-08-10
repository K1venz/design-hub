// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RegisterPage } from './RegisterPage'
import { useAuthStore } from '@/stores/auth-store'

const registerMutation = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  isError: false,
  error: null as Error | null,
}))
const verifyMutation = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  isError: false,
  error: null as Error | null,
}))
const resendMutation = vi.hoisted(() => ({
  mutateAsync: vi.fn(),
  reset: vi.fn(),
  isPending: false,
  isError: false,
  error: null as Error | null,
}))

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

vi.mock('@/api/auth', () => ({
  RegistrationVerificationError: class RegistrationVerificationError extends Error {
    status?: number
  },
  useRegister: () => registerMutation,
  useVerifyRegistration: () => verifyMutation,
  useResendRegistration: () => resendMutation,
}))

function CurrentPath() {
  const location = useLocation()
  return <output data-testid="current-path">{location.pathname}</output>
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/register']}>
      <Routes>
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/home" element={<CurrentPath />} />
      </Routes>
    </MemoryRouter>,
  )
}

function fillDetails() {
  fireEvent.change(screen.getByLabelText('昵称（选填）'), { target: { value: '新设计师' } })
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: ' New.User@Example.com ' } })
  fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'very-secret-password' } })
  fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'very-secret-password' } })
  fireEvent.click(screen.getByRole('checkbox'))
}

async function moveToVerification() {
  fillDetails()
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '发送验证码' }))
  })
  screen.getByRole('heading', { name: '验证邮箱' })
}

beforeEach(() => {
  registerMutation.mutateAsync.mockReset().mockResolvedValue({ message: '验证码已发送' })
  verifyMutation.mutateAsync.mockReset().mockResolvedValue({ jwt: 'verified-session' })
  resendMutation.mutateAsync.mockReset().mockResolvedValue({ message: '验证码已重新发送' })
  registerMutation.isPending = false
  registerMutation.isError = false
  registerMutation.error = null
  verifyMutation.isPending = false
  verifyMutation.isError = false
  verifyMutation.error = null
  resendMutation.isPending = false
  resendMutation.isError = false
  resendMutation.error = null
  localStorage.clear()
  sessionStorage.clear()
  useAuthStore.setState({ token: null, user: null })
})

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('RegisterPage', () => {
  it('submits profile details then shows the masked pending email in the verification step', async () => {
    renderPage()

    await moveToVerification()

    expect(registerMutation.mutateAsync).toHaveBeenCalledWith({
      email: 'new.user@example.com',
      name: '新设计师',
      password: 'very-secret-password',
    })
    expect(screen.getByText('n***r@example.com')).toBeTruthy()
    expect(screen.getByLabelText('验证码').getAttribute('inputmode')).toBe('numeric')
  })

  it('accepts only six ASCII digits and navigates after successful verification', async () => {
    renderPage()
    await moveToVerification()

    const code = screen.getByLabelText('验证码')
    fireEvent.change(code, { target: { value: '12a3４5678' } })
    expect((code as HTMLInputElement).value).toBe('123567')

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '验证并进入 Design Hub' }))
    })

    expect(verifyMutation.mutateAsync).toHaveBeenCalledWith({
      email: 'new.user@example.com',
      code: '123567',
    })
    act(() => useAuthStore.getState().setToken('verified-session'))
    expect(screen.getByTestId('current-path').textContent).toBe('/home')
  })

  it('disables resend for a countdown, enables it afterward, and resends only the pending email', async () => {
    vi.useFakeTimers()
    renderPage()
    await moveToVerification()

    const resend = screen.getByRole('button', { name: '60 秒后可重新发送' })
    expect(resend.hasAttribute('disabled')).toBe(true)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '重新发送验证码' }))
    })

    expect(resendMutation.mutateAsync).toHaveBeenCalledWith({ email: 'new.user@example.com' })
    expect(resendMutation.mutateAsync.mock.calls[0]?.[0]).toEqual({ email: 'new.user@example.com' })
  })

  it('keeps an unclassified verification failure retryable and lets the user return to a fresh details form', async () => {
    verifyMutation.mutateAsync.mockRejectedValue(new Error('验证码已过期'))
    renderPage()
    await moveToVerification()

    fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '验证并进入 Design Hub' }))
    })

    expect(screen.getByRole('alert').textContent).toContain('验证码已过期')
    fireEvent.click(screen.getByRole('button', { name: '返回修改资料' }))

    expect(screen.getByRole('heading', { name: '创建账号' })).toBeTruthy()
    expect((screen.getByLabelText('邮箱') as HTMLInputElement).value).toBe('new.user@example.com')
    expect((screen.getByLabelText('密码') as HTMLInputElement).value).toBe('')
  })

  it('never persists passwords or verification codes in browser storage', async () => {
    renderPage()
    await moveToVerification()
    fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })

    const stored = [localStorage, sessionStorage]
      .flatMap((storage) => Array.from({ length: storage.length }, (_, index) => storage.getItem(storage.key(index)!)))
      .join(' ')
    expect(stored).not.toContain('very-secret-password')
    expect(stored).not.toContain('123456')
  })
})
