import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { OpenVikingWorkspace } from './OpenVikingWorkspace'
import type { OpenVikingProfile } from './hooks/use-app-connection'

const apiMocks = vi.hoisted(() => ({
  createProfile: vi.fn(),
  listProfiles: vi.fn(),
  revokeProfile: vi.fn(),
  updateProfile: vi.fn(),
  validateProfile: vi.fn(),
}))

vi.mock('./api', () => ({
  openVikingApi: apiMocks,
}))

const profile = (
  profileId: string,
  displayName: string,
  status: OpenVikingProfile['status'] = 'ready',
): OpenVikingProfile => ({
  profile_id: profileId,
  display_name: displayName,
  workspace_uri: `viking://workspace/${profileId}/`,
  root_resource_ref: `ovr_${profileId}`,
  status,
  credential_mode: 'managed',
  api_key_configured: true,
  api_key_masked: '••••••••',
  created_at: '2026-08-30T00:00:00Z',
  updated_at: '2026-09-07T08:30:00Z',
})

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/kb/*" element={<OpenVikingWorkspace />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('OpenVikingWorkspace', () => {
  afterEach(cleanup)

  beforeEach(() => {
    window.localStorage.clear()
    Object.values(apiMocks).forEach((mock) => mock.mockReset())
  })

  it('shows all knowledge-base profiles at /kb without a second global sidebar', async () => {
    apiMocks.listProfiles.mockResolvedValue([
      profile('finance', '财务知识库'),
      profile('support', '客服知识库', 'pending'),
    ])

    const { container } = renderRoute('/kb')

    expect(
      await screen.findByRole('heading', { name: '知识库' }),
    ).toBeTruthy()
    expect(
      screen.getByText('财务知识库'),
    ).toBeTruthy()
    expect(screen.getByText('客服知识库')).toBeTruthy()
    expect(screen.getAllByText('平台托管凭据')).toHaveLength(2)
    expect(screen.getByText('viking://workspace/finance/')).toBeTruthy()
    expect(
      screen.getByRole('link', { name: '进入 财务知识库' }).getAttribute('href'),
    ).toBe('/kb/finance/resources')
    expect(container.querySelector('.openviking-module-nav')).toBeNull()
  })

  it('restores a profile detail deep link with Chinese section navigation', async () => {
    apiMocks.listProfiles.mockResolvedValue([
      profile('finance', '财务知识库'),
      profile('support', '客服知识库'),
    ])

    renderRoute('/kb/finance/settings')

    expect(
      await screen.findByRole('heading', { name: '财务知识库' }),
    ).toBeTruthy()
    expect(
      screen.getByRole('navigation', { name: '知识库二级导航' }),
    ).toBeTruthy()
    expect(
      screen.getByRole('link', { name: '资源' }).getAttribute('href'),
    ).toBe('/kb/finance/resources')
    expect(screen.getByRole('heading', { name: '连接设置' })).toBeTruthy()
    expect(screen.getByText('平台托管凭据')).toBeTruthy()
    expect(screen.queryByLabelText('API Key')).toBeNull()
    expect(window.localStorage.getItem('openviking.activeProfileId')).toBe(
      'finance',
    )
  })

  it('creates a managed profile without rendering or submitting credential inputs', async () => {
    const created = profile('legal', '法务知识库', 'pending')
    const ready = profile('legal', '法务知识库')
    apiMocks.listProfiles.mockResolvedValue([])
    apiMocks.createProfile.mockResolvedValue(created)
    apiMocks.validateProfile.mockResolvedValue(ready)

    renderRoute('/kb/new')

    expect(
      await screen.findByRole('heading', { name: '新建知识库' }),
    ).toBeTruthy()
    expect(screen.getByText('平台托管凭据')).toBeTruthy()
    expect(screen.queryByLabelText('API Key')).toBeNull()

    fireEvent.change(screen.getByLabelText('知识库名称'), {
      target: { value: '法务知识库' },
    })
    fireEvent.change(screen.getByLabelText('Workspace URI'), {
      target: { value: 'viking://workspace/legal/' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建知识库' }))

    await waitFor(() => {
      expect(apiMocks.createProfile).toHaveBeenCalledWith({
        display_name: '法务知识库',
        workspace_uri: 'viking://workspace/legal/',
      })
    })
    expect(apiMocks.validateProfile).toHaveBeenCalledWith('legal')
    expect(
      await screen.findByRole('heading', { name: '法务知识库' }),
    ).toBeTruthy()
  })

  it('shows BYOK inputs only when the backend credential policy enables them', async () => {
    apiMocks.listProfiles.mockResolvedValue([])

    render(
      <MemoryRouter initialEntries={['/kb/new']}>
        <Routes>
          <Route
            path="/kb/*"
            element={<OpenVikingWorkspace credentialPolicy="hybrid" />}
          />
        </Routes>
      </MemoryRouter>,
    )

    expect(
      await screen.findByRole('heading', { name: '新建知识库' }),
    ).toBeTruthy()
    expect(screen.queryByLabelText('API Key')).toBeNull()
    fireEvent.click(screen.getByRole('radio', { name: /自有 OpenViking/ }))
    expect(screen.getByLabelText('API Key').getAttribute('type')).toBe(
      'password',
    )
    expect(screen.getByLabelText('Base URL').getAttribute('type')).toBe('url')
  })

  it('deletes one Profile without removing another from the list', async () => {
    const finance = profile('finance', '财务知识库')
    const support = profile('support', '客服知识库')
    apiMocks.listProfiles
      .mockResolvedValueOnce([finance, support])
      .mockResolvedValueOnce([support])
    apiMocks.revokeProfile.mockResolvedValue(undefined)
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderRoute('/kb')
    const financeCard = await screen.findByRole('heading', {
      name: '财务知识库',
    }).then((heading) => heading.closest('article')!)
    fireEvent.click(within(financeCard).getByRole('button', { name: '删除' }))

    await waitFor(() => {
      expect(apiMocks.revokeProfile).toHaveBeenCalledWith('finance')
      expect(screen.queryByText('财务知识库')).toBeNull()
    })
    expect(screen.getByText('客服知识库')).toBeTruthy()
  })
})
