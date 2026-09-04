import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { OpenVikingWorkspace } from './OpenVikingWorkspace'

const apiMocks = vi.hoisted(() => ({
  listProfiles: vi.fn(),
}))

vi.mock('./api', () => ({
  openVikingApi: {
    listProfiles: apiMocks.listProfiles,
  },
}))

describe('OpenVikingWorkspace', () => {
  beforeEach(() => {
    window.localStorage.clear()
    apiMocks.listProfiles.mockReset()
  })

  it('shows an actionable connection state when no profile exists', async () => {
    apiMocks.listProfiles.mockResolvedValue([])

    render(<OpenVikingWorkspace />)

    expect(
      await screen.findByRole('heading', { name: 'Add connection' }),
    ).toBeTruthy()
    expect(screen.getByLabelText('API key').getAttribute('type')).toBe('password')
    expect(
      (screen.getByRole('button', { name: 'Connect' }) as HTMLButtonElement)
        .disabled,
    ).toBe(false)
    expect(screen.queryByRole('alert')).toBeNull()
  })
})
