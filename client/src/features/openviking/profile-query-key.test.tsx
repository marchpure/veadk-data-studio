import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook } from '@testing-library/react'
import type { ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { AppConnectionProvider, type OpenVikingProfile } from './hooks/use-app-connection'
import { useVikingFsList } from './routes/resources/-hooks/viking-fm'

const profile = (profileId: string): OpenVikingProfile => ({
  profile_id: profileId,
  display_name: profileId,
  workspace_uri: 'viking://workspace/',
  root_resource_ref: `ovr_${profileId}`,
  status: 'ready',
  credential_mode: 'managed',
  created_at: 0,
  updated_at: 0,
})

describe('OpenViking query isolation', () => {
  it('partitions resource queries by active Profile', () => {
    const queryClient = new QueryClient()
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>
        <AppConnectionProvider profile={profile('finance')}>
          {children}
        </AppConnectionProvider>
      </QueryClientProvider>
    )
    const { result } = renderHook(
      () => useVikingFsList('viking://workspace/', {}, false),
      { wrapper },
    )

    expect(result.current.dataUpdatedAt).toBe(0)
    expect(
      queryClient.getQueryCache().getAll().map((query) => query.queryKey),
    ).toContainEqual([
      'viking-fs-ls',
      'finance',
      'viking://workspace/',
      {},
    ])
  })
})
