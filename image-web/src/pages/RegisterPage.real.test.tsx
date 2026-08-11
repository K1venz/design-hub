// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { act } from 'react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { RegisterPage } from './RegisterPage'
import { useAuthStore } from '@/stores/auth-store'

const { fetchMock } = vi.hoisted(() => {
  const fetchMock = vi.fn()
  const NativeRequest = globalThis.Request
  class RelativeRequest extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(typeof input === 'string' && input.startsWith('/') ? new URL(input, 'http://localhost') : input, init)
    }
  }
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('Request', RelativeRequest)
  return { fetchMock }
})

vi.mock('@/api/crypto', () => ({
  encryptSecret: vi.fn(async () => 'encrypted-password'),
}))

;(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true

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
      <MemoryRouter initialEntries={['/register']}>
        <Routes>
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/home" element={<CurrentPath />} />
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

async function fillAndSubmitDetails() {
  fireEvent.change(screen.getByLabelText('邮箱'), { target: { value: 'new.user@example.com' } })
  fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'very-secret-password' } })
  fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'very-secret-password' } })
  fireEvent.click(screen.getByRole('checkbox'))
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: '发送验证码' }))
  })
}

function cacheText(client: QueryClient): string {
  return client
    .getMutationCache()
    .getAll()
    .map((mutation) => JSON.stringify(mutation.state.variables))
    .join('\n')
}

beforeEach(() => {
  fetchMock.mockReset()
  localStorage.clear()
  sessionStorage.clear()
  useAuthStore.setState({ token: null, user: null })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('RegisterPage sensitive mutation lifecycle', () => {
  it('removes the registration password from form state and the real mutation cache after an acknowledgement', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        message: '验证码已发送',
        challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      }),
    )
    const { client } = renderPage()

    await fillAndSubmitDetails()

    expect((screen.getByLabelText('验证码') as HTMLInputElement).value).toBe('')
    expect(cacheText(client)).not.toContain('very-secret-password')
  })

  it('removes the registration password after a failed request too', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: '服务暂时不可用' }, 500))
    const { client } = renderPage()

    await fillAndSubmitDetails()

    expect((screen.getByLabelText('密码') as HTMLInputElement).value).toBe('')
    expect(cacheText(client)).not.toContain('very-secret-password')
  })

  it('uses the real verification hook to set the session and navigate, then removes the code from cache', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          message: '验证码已发送',
          challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ jwt: 'verified-session', role: '设计师', name: '新设计师' }))
    const { client } = renderPage()

    await fillAndSubmitDetails()
    fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '验证并进入 Design Hub' }))
    })

    expect(useAuthStore.getState().token).toBe('verified-session')
    expect(screen.getByTestId('current-path').textContent).toBe('/home')
    expect(cacheText(client)).not.toContain('123456')
  })

  it('only marks a backend 400 verification response as invalid or expired', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          message: '验证码已发送',
          challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ detail: '验证码错误或已过期' }, 400))
    const { client } = renderPage()

    await fillAndSubmitDetails()
    fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '验证并进入 Design Hub' }))
    })

    expect(screen.getByRole('alert').textContent).toContain('验证码无效或已过期')
    expect(screen.getAllByText('验证码无效或已过期。请重新输入，或重新发送验证码。')).toHaveLength(1)
    expect((screen.getByLabelText('验证码') as HTMLInputElement).value).toBe('')
    expect(cacheText(client)).not.toContain('123456')
  })

  it('shows a retryable service message instead of an invalid-code message for a 500 verification response', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          message: '验证码已发送',
          challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ detail: '服务暂时不可用' }, 500))
    renderPage()

    await fillAndSubmitDetails()
    fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '验证并进入 Design Hub' }))
    })

    expect(screen.getByRole('alert').textContent).toContain('验证暂时无法完成，请稍后重试。')
    expect(screen.queryByText('验证码无效或已过期。请重新输入，或重新发送验证码。')).toBeNull()
  })

  it('keeps the rate-limit response distinct and retryable', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          message: '验证码已发送',
          challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ detail: '请求过于频繁' }, 429))
    renderPage()

    await fillAndSubmitDetails()
    fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '验证并进入 Design Hub' }))
    })

    expect(screen.getByRole('alert').textContent).toContain('尝试太频繁，请稍等 1 分钟再试')
  })

  it('keeps a network failure retryable instead of presenting an invalid-code message', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          message: '验证码已发送',
          challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      )
      .mockRejectedValueOnce(new Error('offline'))
    renderPage()

    await fillAndSubmitDetails()
    fireEvent.change(screen.getByLabelText('验证码'), { target: { value: '123456' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '验证并进入 Design Hub' }))
    })

    expect(screen.getByRole('alert').textContent).toContain('网络异常，请检查连接后重试')
  })

  it('cleans up the verification countdown when the page unmounts', async () => {
    vi.useFakeTimers()
    fetchMock.mockResolvedValue(
      jsonResponse({
        message: '验证码已发送',
        challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      }),
    )
    const clearTimer = vi.spyOn(window, 'clearInterval')
    const { unmount } = renderPage()

    await fillAndSubmitDetails()
    unmount()

    expect(clearTimer).toHaveBeenCalled()
    vi.useRealTimers()
  })

  it('stops the old countdown before restarting verification and runs only the new countdown', async () => {
    vi.useFakeTimers()
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          message: '验证码已发送',
          challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse({
          message: '验证码已发送',
          challenge_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
        }),
      )
    renderPage()

    await fillAndSubmitDetails()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(screen.getByRole('button', { name: '50 秒后可重新发送' }).hasAttribute('disabled')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '返回修改资料' }))
    fireEvent.change(screen.getByLabelText('密码'), { target: { value: 'very-secret-password' } })
    fireEvent.change(screen.getByLabelText('确认密码'), { target: { value: 'very-secret-password' } })
    fireEvent.click(screen.getByRole('checkbox'))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '发送验证码' }))
    })

    expect(screen.getByRole('button', { name: '60 秒后可重新发送' }).hasAttribute('disabled')).toBe(true)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1_000)
    })
    expect(screen.getByRole('button', { name: '59 秒后可重新发送' }).hasAttribute('disabled')).toBe(true)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29_000)
    })
    expect(screen.getByRole('button', { name: '30 秒后可重新发送' }).hasAttribute('disabled')).toBe(true)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })
    expect(screen.getByRole('button', { name: '重新发送验证码' }).hasAttribute('disabled')).toBe(false)
    vi.useRealTimers()
  })
})
