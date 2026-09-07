// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'

import { DataWorkshopApp } from './DataWorkshopApp'

vi.mock('./components/WorkshopShell', () => ({
  WorkshopShell: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))
vi.mock('./pages/OpenConnectorSurface', () => ({
  OpenConnectorSurface: ({ surface, resourcePath = '' }: { surface: string; resourcePath?: string }) => (
    <div data-testid="openconnector-surface">{surface}{resourcePath}</div>
  ),
}))
vi.mock('./pages/Docs', () => ({ ConnectionDocs: () => <div>连接文档</div> }))
vi.mock('./pages/Home', () => ({ WorkshopHome: () => <div>首页</div> }))
vi.mock('./pages/SkillMount', () => ({ SkillMount: () => <div>Skill</div> }))
vi.mock('../../pages/OpenVikingPage', () => ({ default: () => <div>知识库</div> }))
vi.mock('./api', () => ({
  workshopApi: {
    getBootstrap: vi.fn().mockResolvedValue({ backend_mode: 'REAL' }),
  },
}))

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

function renderRoute(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <DataWorkshopApp />
      <LocationProbe />
    </MemoryRouter>,
  )
}

afterEach(cleanup)

describe('DataWorkshopApp routes', () => {
  it.each([
    ['/connections/overview', 'overview'],
    ['/connections/providers', 'providers'],
    ['/connections/marketplace', 'marketplace'],
    ['/connections/actions', 'actions'],
    ['/connections/runs', 'runs'],
    ['/connections/access', 'access'],
  ])('owns %s with the canonical OpenConnector surface', (path, surface) => {
    renderRoute(path)
    expect(screen.getByTestId('openconnector-surface').textContent).toBe(surface)
  })

  it('preserves a provider detail route inside the owned provider surface', () => {
    renderRoute('/connections/providers/oracle')
    expect(screen.getByTestId('openconnector-surface').textContent).toBe('providers/oracle')
  })

  it('maps action detail ids to the actions OpenConnector resource', () => {
    renderRoute('/connections/actions/oracle.query_rows')
    expect(screen.getByTestId('openconnector-surface').textContent).toBe('actions/oracle.query_rows')
  })

  it.each([
    ['/connections/trace', '/connections/runs'],
    ['/connections/providers/market', '/connections/providers'],
    ['/connections/providers/new/oracle', '/connections/providers'],
    ['/connections/access/identity', '/connections/access'],
    ['/kb/connect', '/kb/new'],
  ])('redirects legacy route %s to %s', async (legacy, canonical) => {
    renderRoute(legacy)
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe(canonical))
  })
})
