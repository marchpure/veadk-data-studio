import { beforeEach, describe, expect, it, vi } from 'vitest'

import { openVikingApi, selectConnectionResources } from './api'

const apiFetchMock = vi.hoisted(() => vi.fn())

vi.mock('../../services/api', () => ({
  apiFetch: apiFetchMock,
}))

describe('selectConnectionResources', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  it('exposes only importable Source Resources from unified datasources', () => {
    expect(
      selectConnectionResources([
        {
          id: 'source-1',
          name: 'Approved source',
          resource_type: 'web',
          source_type: 'source_resource',
          status: 'ready',
        },
        {
          id: 'connection-1',
          name: 'Database',
          source_type: 'connection',
          type: 'postgresql',
        },
      ]),
    ).toEqual([
      {
        resource_id: 'source-1',
        kind: 'web',
        display_name: 'Approved source',
        status: 'ready',
      },
    ])
  })

  it('sends a BYOK key only in the create request body', async () => {
    apiFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          data: {
            profile_id: 'finance',
            display_name: '财务知识库',
            workspace_uri: 'opaque-workspace',
            root_resource_ref: 'ovr_finance',
            credential_mode: 'byok',
            status: 'pending',
            created_at: 0,
            updated_at: 0,
          },
        }),
        { headers: { 'content-type': 'application/json' }, status: 201 },
      ),
    )

    await openVikingApi.createProfile({
      api_key: 'secret-value',
      base_url: 'https://openviking.example.test',
      credential_mode: 'byok',
      display_name: '财务知识库',
      workspace_uri: 'viking://resources/',
    })

    const [url, init] = apiFetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).not.toContain('secret-value')
    expect(new Headers(init.headers).has('X-API-Key')).toBe(false)
    expect(JSON.parse(String(init.body))).toMatchObject({
      api_key: 'secret-value',
      credential_mode: 'byok',
    })
  })
})
