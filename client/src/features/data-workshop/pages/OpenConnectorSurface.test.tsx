// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, useLocation } from 'react-router-dom'

import { workshopApi } from '../api'
import { OpenConnectorSurface } from './OpenConnectorSurface'

vi.mock('../api', () => ({
  workshopApi: {
    createLaunchSession: vi.fn(),
  },
}))

const createLaunchSession = vi.mocked(workshopApi.createLaunchSession)

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}

function surfaceView(surface: 'overview' | 'actions' | 'runs') {
  const titles = { overview: '总览', actions: '操作', runs: '运行记录' }
  return <OpenConnectorSurface surface={surface} title={titles[surface]} />
}

function view(surface: 'overview' | 'actions' | 'runs') {
  return (
    <MemoryRouter>
      {surfaceView(surface)}
    </MemoryRouter>
  )
}

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}{location.search}</output>
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('OpenConnectorSurface', () => {
  it('keeps one iframe and shows a visible transition while switching surfaces', async () => {
    createLaunchSession
      .mockResolvedValueOnce({ launch_url: '/oc/overview?embed=studio', expires_at: 1000 })
      .mockResolvedValueOnce({ launch_url: '/oc/actions?embed=studio', expires_at: 1001 })

    const rendered = render(view('overview'))
    const iframe = await screen.findByTitle('OpenConnector 总览')
    fireEvent.load(iframe)
    expect(screen.queryByText('正在切换到总览…')).toBeNull()

    rendered.rerender(view('actions'))
    expect(screen.getByText('正在切换到操作…')).toBeTruthy()
    await waitFor(() => expect(createLaunchSession).toHaveBeenLastCalledWith('actions', '', ''))

    expect(screen.getByTitle('OpenConnector 操作')).toBe(iframe)
    expect(iframe.getAttribute('src')).toBe('/oc/overview?embed=studio')
  })

  it('lets the newest rapid navigation win when launch requests resolve out of order', async () => {
    const overview = deferred<{ launch_url: string; expires_at: number }>()
    const runs = deferred<{ launch_url: string; expires_at: number }>()
    createLaunchSession
      .mockReturnValueOnce(overview.promise)
      .mockReturnValueOnce(runs.promise)

    const rendered = render(view('overview'))
    rendered.rerender(view('actions'))
    rendered.rerender(view('runs'))

    overview.resolve({ launch_url: '/oc/overview?embed=studio', expires_at: 1000 })
    runs.resolve({ launch_url: '/oc/runs?embed=studio', expires_at: 1002 })

    const iframe = await screen.findByTitle('OpenConnector 运行记录')
    expect(iframe.getAttribute('src')).toBe('/oc/runs?embed=studio')
    expect(screen.queryByTitle('OpenConnector 操作')).toBeNull()
    expect(screen.queryByTitle('OpenConnector 总览')).toBeNull()
  })

  it('accepts a same-origin iframe card navigation and ignores an unsafe route', async () => {
    createLaunchSession.mockResolvedValue({
      launch_url: '/oc/overview?embed=studio',
      expires_at: 1000,
    })
    render(
      <MemoryRouter initialEntries={['/connections/overview']}>
        {surfaceView('overview')}
        <LocationProbe />
      </MemoryRouter>,
    )
    const iframe = await screen.findByTitle('OpenConnector 总览') as HTMLIFrameElement
    fireEvent.load(iframe)
    window.dispatchEvent(new MessageEvent('message', {
      origin: window.location.origin,
      source: iframe.contentWindow,
      data: {
        type: 'openconnector.route.changed',
        version: 1,
        surface: 'overview',
        resourcePath: '',
        search: '',
      },
    }))

    window.dispatchEvent(new MessageEvent('message', {
      origin: window.location.origin,
      source: iframe.contentWindow,
      data: {
        type: 'openconnector.route.changed',
        version: 1,
        surface: 'providers',
        resourcePath: '/oracle',
        search: '',
      },
    }))
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/connections/providers/oracle'))
    expect(screen.queryByText('正在切换到总览…')).toBeNull()

    window.dispatchEvent(new MessageEvent('message', {
      origin: window.location.origin,
      source: iframe.contentWindow,
      data: {
        type: 'openconnector.route.changed',
        version: 1,
        surface: 'access',
        resourcePath: '/../admin',
        search: '?token=secret',
      },
    }))
    expect(screen.getByTestId('location').textContent).toBe('/connections/providers/oracle')
  })

  it('ignores a stale iframe route event while the newest parent navigation is pending', async () => {
    createLaunchSession
      .mockResolvedValueOnce({ launch_url: '/oc/overview?embed=studio', expires_at: 1000 })
      .mockResolvedValueOnce({ launch_url: '/oc/runs?embed=studio', expires_at: 1001 })
    const rendered = render(view('overview'))
    const iframe = await screen.findByTitle('OpenConnector 总览') as HTMLIFrameElement
    fireEvent.load(iframe)
    rendered.rerender(view('runs'))
    await waitFor(() => expect(createLaunchSession).toHaveBeenLastCalledWith('runs', '', ''))

    window.dispatchEvent(new MessageEvent('message', {
      origin: window.location.origin,
      source: iframe.contentWindow,
      data: {
        type: 'openconnector.route.changed',
        version: 1,
        surface: 'overview',
        resourcePath: '',
        search: '',
      },
    }))
    expect(screen.getByText('正在切换到运行记录…')).toBeTruthy()

    window.dispatchEvent(new MessageEvent('message', {
      origin: window.location.origin,
      source: iframe.contentWindow,
      data: {
        type: 'openconnector.route.changed',
        version: 1,
        surface: 'runs',
        resourcePath: '',
        search: '',
      },
    }))
    await waitFor(() => expect(screen.queryByText('正在切换到运行记录…')).toBeNull())
  })
})
