import { afterEach, describe, expect, it } from 'vitest'

import { setActiveOpenVikingProfileId } from '../../hooks/use-app-connection'
import {
  clearOpenVikingResourceRefs,
  getOpenVikingResourceRef,
  registerOpenVikingRoot,
} from './resource-ref-registry'

describe('OpenViking ResourceRef isolation', () => {
  afterEach(() => {
    clearOpenVikingResourceRefs()
    setActiveOpenVikingProfileId('')
  })

  it('keeps the same workspace URI isolated between profiles', () => {
    setActiveOpenVikingProfileId('finance')
    registerOpenVikingRoot('viking://workspace/', 'ovr_finance')

    setActiveOpenVikingProfileId('support')
    expect(getOpenVikingResourceRef('viking://workspace/')).toBeUndefined()
    registerOpenVikingRoot('viking://workspace/', 'ovr_support')

    expect(getOpenVikingResourceRef('viking://workspace/')).toBe('ovr_support')
    setActiveOpenVikingProfileId('finance')
    expect(getOpenVikingResourceRef('viking://workspace/')).toBe('ovr_finance')
  })
})
