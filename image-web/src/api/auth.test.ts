// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAuthStore } from '@/stores/auth-store'

const fetchMock = vi.hoisted(() => vi.fn())
const NativeRequest = globalThis.Request

class RelativeRequest extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const resolved = typeof input === 'string' && input.startsWith('/') ? new URL(input, 'http://localhost') : input
    super(resolved, init)
  }
}

vi.mock('@/api/crypto', () => ({
  encryptSecret: vi.fn(async () => 'encrypted-password'),
}))
vi.stubGlobal('fetch', fetchMock)
vi.stubGlobal('Request', RelativeRequest)

type Mutation<V> = {
  mutateAsync: (variables: V) => Promise<unknown>
}

type RegistrationApi = {
  useRegister: () => Mutation<{ email: string; name: string; password: string }>
  useVerifyRegistration?: () => Mutation<{ email: string; code: string }>
  useResendRegistration?: () => Mutation<{ email: string }>
}

async function registrationApi(): Promise<RegistrationApi> {
  return import('@/api/auth') as Promise<RegistrationApi>
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  })
  return createElement(QueryClientProvider, { client }, children)
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function requestBody(fetchMock: ReturnType<typeof vi.fn>): Promise<unknown> {
  const request = fetchMock.mock.calls[0]?.[0] as Request
  return request.json()
}

beforeEach(() => {
  fetchMock.mockReset()
  useAuthStore.setState({ token: null, user: null })
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('registration API mutations', () => {
  it('requests a verification code and leaves the auth session untouched', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ message: 'Code sent' }))
    const auth = await registrationApi()
    const { result } = renderHook(() => auth.useRegister(), { wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          email: 'new.user@example.com',
          name: 'New User',
          password: 'example-password',
        }),
      ).resolves.toEqual({ message: 'Code sent' })
    })

    expect(new URL((fetchMock.mock.calls[0]?.[0] as Request).url).pathname).toBe('/api/auth/register')
    await expect(requestBody(fetchMock)).resolves.toEqual({
      email: 'new.user@example.com',
      name: 'New User',
      password: 'encrypted-password',
    })
    expect(useAuthStore.getState().token).toBeNull()
  })

  it('verifies using only the email and code, then persists the returned session', async () => {
    const auth = await registrationApi()
    const useVerifyRegistration = (auth as RegistrationApi).useVerifyRegistration
    expect(useVerifyRegistration).toBeTypeOf('function')
    if (!useVerifyRegistration) return

    fetchMock.mockResolvedValue(
      jsonResponse({ jwt: 'verified-session', role: 'designer', name: 'New User' }),
    )
    const { result } = renderHook(() => useVerifyRegistration(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({ email: 'new.user@example.com', code: '123456' })
    })

    expect(new URL((fetchMock.mock.calls[0]?.[0] as Request).url).pathname).toBe(
      '/api/auth/register/verify',
    )
    await expect(requestBody(fetchMock)).resolves.toEqual({
      email: 'new.user@example.com',
      code: '123456',
    })
    expect(useAuthStore.getState().token).toBe('verified-session')
  })

  it('resends a verification code using only the email', async () => {
    const auth = await registrationApi()
    const useResendRegistration = (auth as RegistrationApi).useResendRegistration
    expect(useResendRegistration).toBeTypeOf('function')
    if (!useResendRegistration) return

    fetchMock.mockResolvedValue(jsonResponse({ message: 'Code resent' }))
    const { result } = renderHook(() => useResendRegistration(), { wrapper })

    await act(async () => {
      await expect(result.current.mutateAsync({ email: 'new.user@example.com' })).resolves.toEqual({
        message: 'Code resent',
      })
    })

    expect(new URL((fetchMock.mock.calls[0]?.[0] as Request).url).pathname).toBe(
      '/api/auth/register/resend',
    )
    await expect(requestBody(fetchMock)).resolves.toEqual({ email: 'new.user@example.com' })
  })
})
