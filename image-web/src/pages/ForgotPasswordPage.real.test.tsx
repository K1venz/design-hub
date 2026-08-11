// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ForgotPasswordPage } from './ForgotPasswordPage'
import { useAuthStore } from '@/stores/auth-store'

const { encryptSecretMock, fetchMock } = vi.hoisted(() => {
  const fetchMock = vi.fn()
  const NativeRequest = globalThis.Request
  class RelativeRequest extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(
        typeof input === 'string' && input.startsWith('/')
          ? new URL(input, 'http://localhost')
          : input,
        init,
      )
    }
  }
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('Request', RelativeRequest)
  return { encryptSecretMock: vi.fn(async () => 'encrypted-password'), fetchMock }
})

vi.mock('@/api/crypto', () => ({
  encryptSecret: encryptSecretMock,
}))

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true

function CurrentPath() {
  return <output data-testid="current-path">{useLocation().pathname}</output>
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
}

function renderPage(client = makeClient()) {
  const result = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/forgot-password']}>
        <Routes>
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/login" element={<CurrentPath />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...result, client }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function cacheText(client: QueryClient): string {
  return client
    .getMutationCache()
    .getAll()
    .map((mutation) => JSON.stringify(mutation.state.variables))
    .join('\n')
}

function storageText(): string {
  return [localStorage, sessionStorage]
    .flatMap((storage) =>
      Array.from({ length: storage.length }, (_, index) => {
        const key = storage.key(index)
        return key === null ? '' : `${key} ${storage.getItem(key) ?? ''}`
      }),
    )
    .join('\n')
}

async function requestCode() {
  fireEvent.change(screen.getByLabelText('邮箱'), {
    target: { value: 'reset.user@example.com' },
  })
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '发送验证码' }))
  })
}

function fillResetForm() {
  fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })
  fireEvent.change(screen.getByLabelText('新密码'), {
    target: { value: 'very-secret-password' },
  })
  fireEvent.change(screen.getByLabelText('确认新密码'), {
    target: { value: 'very-secret-password' },
  })
}

beforeEach(() => {
  fetchMock.mockReset()
  encryptSecretMock.mockReset().mockResolvedValue('encrypted-password')
  localStorage.clear()
  sessionStorage.clear()
  useAuthStore.setState({ token: null, user: null })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('ForgotPasswordPage sensitive mutation lifecycle', () => {
  it('completes the real reset request and removes the code and password from mutation cache', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ message: '验证码已发送' }))
      .mockResolvedValueOnce(jsonResponse({ message: '密码已重置' }))
    const { client } = renderPage()

    await requestCode()
    fillResetForm()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '重置密码' }))
    })

    expect(screen.getByText('密码已重置成功。请返回登录页，使用新密码登录。')).toBeTruthy()
    expect(encryptSecretMock).toHaveBeenCalledWith('very-secret-password')
    expect(cacheText(client)).not.toContain('very-secret-password')
    expect(cacheText(client)).not.toContain('123456')
    expect(storageText()).not.toContain('very-secret-password')
    expect(storageText()).not.toContain('123456')
  })

  it('clears reset secrets and preserves the backend error after a rejected code', async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ message: '验证码已发送' }))
      .mockResolvedValueOnce(jsonResponse({ detail: '验证码错误或已过期' }, 400))
    const { client } = renderPage()

    await requestCode()
    fillResetForm()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '重置密码' }))
    })

    expect(screen.getByRole('alert').textContent).toContain('验证码错误或已过期')
    expect((screen.getByLabelText('验证码') as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText('新密码') as HTMLInputElement).value).toBe('')
    expect((screen.getByLabelText('确认新密码') as HTMLInputElement).value).toBe('')
    expect(cacheText(client)).not.toContain('very-secret-password')
    expect(cacheText(client)).not.toContain('123456')
  })
})
