import { afterEach, describe, expect, it, vi } from 'vitest'

const apiFetch = vi.hoisted(() => vi.fn())

vi.mock('../../../services/api', () => ({ apiFetch }))

import { SKILL_REQUEST_TIMEOUT_MS, SkillApiTimeoutError, skillApi } from './api'

describe('skillApi request lifecycle', () => {
  afterEach(() => {
    vi.useRealTimers()
    apiFetch.mockReset()
  })

  it('aborts a pending request and reports timeout', async () => {
    vi.useFakeTimers()
    apiFetch.mockImplementation((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    const request = skillApi.listSkills()
    const assertion = expect(request).rejects.toBeInstanceOf(SkillApiTimeoutError)
    await vi.advanceTimersByTimeAsync(SKILL_REQUEST_TIMEOUT_MS)
    await assertion
    expect(apiFetch.mock.calls[0][1].signal.aborted).toBe(true)
  })

  it('forwards route cancellation to the underlying request', async () => {
    const route = new AbortController()
    apiFetch.mockImplementation((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))
    }))
    const request = skillApi.catalog({ signal: route.signal })
    const assertion = expect(request).rejects.toMatchObject({ name: 'AbortError' })
    route.abort()
    await assertion
    expect(apiFetch.mock.calls[0][1].signal.aborted).toBe(true)
  })
})
