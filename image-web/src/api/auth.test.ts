// @vitest-environment jsdom

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { createElement, type ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AUTH_STORAGE_KEY, useAuthStore } from '@/stores/auth-store'
import { setAuthPersistent } from '@/stores/auth-storage'

const { encryptSecretMock, fetchMock } = vi.hoisted(() => ({
  encryptSecretMock: vi.fn(async () => 'encrypted-password'),
  fetchMock: vi.fn(),
}))
const NativeRequest = globalThis.Request

class RelativeRequest extends NativeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    const resolved = typeof input === 'string' && input.startsWith('/') ? new URL(input, 'http://localhost') : input
    super(resolved, init)
  }
}

vi.mock('@/api/crypto', () => ({
  encryptSecret: encryptSecretMock,
}))
vi.stubGlobal('fetch', fetchMock)
vi.stubGlobal('Request', RelativeRequest)

type Mutation<V> = {
  mutateAsync: (variables: V) => Promise<unknown>
}

type RegistrationApi = {
  useRegister: () => Mutation<{ email: string; name: string; password: string }>
  useVerifyRegistration?: () => Mutation<{ email: string; challengeId: string; code: string }>
  useResendRegistration?: () => Mutation<{ email: string; challengeId: string }>
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
  encryptSecretMock.mockReset().mockResolvedValue('encrypted-password')
  setAuthPersistent(true)
  useAuthStore.setState({ token: null, user: null })
  localStorage.clear()
  sessionStorage.clear()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('registration API mutations', () => {
  it('requests a verification code and leaves the complete auth session and storage untouched', async () => {
    const existingUser = {
      user_id: 'existing-user',
      name: 'Existing User',
      role: '设计师' as const,
      dept: null,
    }
    useAuthStore.setState({ token: 'existing-session', user: existingUser })
    const stateBefore = {
      token: useAuthStore.getState().token,
      user: useAuthStore.getState().user,
    }
    const storageBefore = {
      local: localStorage.getItem(AUTH_STORAGE_KEY),
      session: sessionStorage.getItem(AUTH_STORAGE_KEY),
    }
    fetchMock.mockResolvedValue(
      jsonResponse({ message: 'Code sent', challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' }),
    )
    const auth = await registrationApi()
    const { result } = renderHook(() => auth.useRegister(), { wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          email: 'new.user@example.com',
          name: 'New User',
          password: 'example-password',
        }),
      ).resolves.toEqual({
        message: 'Code sent',
        challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      })
    })

    expect(new URL((fetchMock.mock.calls[0]?.[0] as Request).url).pathname).toBe('/api/auth/register')
    await expect(requestBody(fetchMock)).resolves.toEqual({
      email: 'new.user@example.com',
      name: 'New User',
      password: 'encrypted-password',
    })
    expect({
      token: useAuthStore.getState().token,
      user: useAuthStore.getState().user,
    }).toEqual(stateBefore)
    expect({
      local: localStorage.getItem(AUTH_STORAGE_KEY),
      session: sessionStorage.getItem(AUTH_STORAGE_KEY),
    }).toEqual(storageBefore)
  })

  it('stops before HTTP when password encryption fails', async () => {
    encryptSecretMock.mockRejectedValueOnce(new Error('encryption unavailable'))
    const auth = await registrationApi()
    const { result } = renderHook(() => auth.useRegister(), { wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          email: 'new.user@example.com',
          name: 'New User',
          password: 'example-password',
        }),
      ).rejects.toThrow('encryption unavailable')
    })

    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('verifies using the initiating challenge, then persists the returned session', async () => {
    const auth = await registrationApi()
    const useVerifyRegistration = (auth as RegistrationApi).useVerifyRegistration
    expect(useVerifyRegistration).toBeTypeOf('function')
    if (!useVerifyRegistration) return

    fetchMock.mockResolvedValue(
      jsonResponse({ jwt: 'verified-session', role: 'designer', name: 'New User' }),
    )
    const { result } = renderHook(() => useVerifyRegistration(), { wrapper })

    await act(async () => {
      await result.current.mutateAsync({
        email: 'new.user@example.com',
        challengeId: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        code: '123456',
      })
    })

    expect(new URL((fetchMock.mock.calls[0]?.[0] as Request).url).pathname).toBe(
      '/api/auth/register/verify',
    )
    await expect(requestBody(fetchMock)).resolves.toEqual({
      email: 'new.user@example.com',
      challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
      code: '123456',
    })
    expect(useAuthStore.getState().token).toBe('verified-session')
  })

  it('resends using the initiating challenge and returns the rotated challenge', async () => {
    const auth = await registrationApi()
    const useResendRegistration = (auth as RegistrationApi).useResendRegistration
    expect(useResendRegistration).toBeTypeOf('function')
    if (!useResendRegistration) return

    fetchMock.mockResolvedValue(
      jsonResponse({ message: 'Code resent', challenge_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' }),
    )
    const { result } = renderHook(() => useResendRegistration(), { wrapper })

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          email: 'new.user@example.com',
          challengeId: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
        }),
      ).resolves.toEqual({
        message: 'Code resent',
        challenge_id: 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
      })
    })

    expect(new URL((fetchMock.mock.calls[0]?.[0] as Request).url).pathname).toBe(
      '/api/auth/register/resend',
    )
    await expect(requestBody(fetchMock)).resolves.toEqual({
      email: 'new.user@example.com',
      challenge_id: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
    })
  })
})
