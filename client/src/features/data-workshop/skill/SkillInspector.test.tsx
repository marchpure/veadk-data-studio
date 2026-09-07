// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { SkillInspector } from './SkillInspector'
import type { SkillSession } from './types'

vi.mock('./ArtifactPanel', () => ({
  ArtifactPanel: () => <div data-testid="artifact-panel">Artifact</div>,
}))

afterEach(cleanup)

const session = (status: SkillSession['status']): SkillSession => ({
  id: 'session-1',
  skill_id: 'skill-1',
  title: '营收复盘',
  status,
  context_refs: { mcp_refs: [], knowledge_refs: [] },
  messages: [],
  events: [],
})

describe('SkillInspector', () => {
  it('keeps failure history visible without pretending it is current success', () => {
    render(<SkillInspector skillId="skill-1" session={session('retryable')} revisions={[]} />)

    expect(screen.getByText('本轮未完成')).toBeTruthy()
    expect(screen.getByText('失败记录已保留在对话中')).toBeTruthy()
    expect(screen.queryByText('已就绪')).toBeNull()
    expect(screen.getByText('如何使用')).toBeTruthy()
  })

  it('shows artifact and usage guidance when ready', () => {
    render(<SkillInspector skillId="skill-1" session={{
      ...session('ready'),
      artifact: {
        revision: 'r1',
        preview_url: '/preview',
        download_url: '/download',
      },
    }} revisions={[]} />)

    expect(screen.getByTestId('artifact-panel')).toBeTruthy()
    expect(screen.getByText('开始一次对话')).toBeTruthy()
  })
})
