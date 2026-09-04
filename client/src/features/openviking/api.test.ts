import { describe, expect, it } from 'vitest'

import { selectConnectionResources } from './api'

describe('selectConnectionResources', () => {
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
})
