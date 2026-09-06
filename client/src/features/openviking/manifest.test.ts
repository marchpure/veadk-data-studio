import { afterEach, describe, expect, it, vi } from 'vitest'

import { openVikingManifest } from './manifest'

describe('openVikingManifest', () => {
  afterEach(() => {
    window.history.replaceState({}, '', '/')
  })

  it('opens the knowledge-base creation route', () => {
    const listener = vi.fn()
    window.addEventListener('popstate', listener)

    openVikingManifest.slots.createKnowledgeBase.run()

    expect(window.location.pathname).toBe('/kb/new')
    expect(listener).toHaveBeenCalledOnce()
    window.removeEventListener('popstate', listener)
  })
})
