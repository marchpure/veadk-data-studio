// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { SkillMount } from './SkillMount'
import type { SkillContextRef, SkillSession, WorkshopSkill } from '../skill/types'

const apiMocks = vi.hoisted(() => ({
  catalog: vi.fn(),
  listSkills: vi.fn(),
  createSkill: vi.fn(),
  invoke: vi.fn(),
  events: vi.fn(),
}))

vi.mock('../skill/api', () => ({
  skillApi: {
    catalog: apiMocks.catalog,
    listSkills: apiMocks.listSkills,
    createSkill: apiMocks.createSkill,
    invoke: apiMocks.invoke,
    events: apiMocks.events,
    listSessions: vi.fn(),
    revisions: vi.fn(),
    getSession: vi.fn(),
    createSession: vi.fn(),
    updateContext: vi.fn(),
    cancel: vi.fn(),
    retry: vi.fn(),
  },
}))

vi.mock('../../openviking/api', () => ({
  openVikingApi: { resolveResource: vi.fn() },
}))

const action: SkillContextRef = {
  id: 'orders.list',
  kind: 'mcp_action',
  name: '查询订单',
  source: 'OpenConnector',
  connection_id: 'orders',
  metadata: {},
}

function created(body: {
  title: string
  target_skill: string
  description: string
  mcp_refs: SkillContextRef[]
  knowledge_refs: SkillContextRef[]
}) {
  const skill: WorkshopSkill = {
    id: 'skill-1',
    ...body,
    status: 'draft',
    context_refs: { mcp_refs: body.mcp_refs, knowledge_refs: body.knowledge_refs },
  }
  const session: SkillSession = {
    id: 'session-1',
    skill_id: skill.id,
    title: '初始会话',
    status: 'draft',
    context_refs: skill.context_refs,
    messages: [],
    events: [],
  }
  return { skill, session }
}

function renderNewSkill() {
  return render(
    <MemoryRouter initialEntries={['/skill?mode=new']}>
      <SkillMount />
    </MemoryRouter>,
  )
}

describe('SkillMount creation flow', () => {
  beforeEach(() => {
    Object.values(apiMocks).forEach(mock => mock.mockReset())
    apiMocks.listSkills.mockResolvedValue({ items: [], total: 0 })
    apiMocks.catalog.mockResolvedValue({
      backend: 'REAL',
      w5_configured: true,
      connections: [{ id: 'orders', name: '订单库', provider: 'internal', actions: [action] }],
      knowledge_refs: [],
    })
    apiMocks.createSkill.mockImplementation(async body => created(body))
    apiMocks.events.mockResolvedValue({ items: [], next: 0, done: false, status: 'running' })
    apiMocks.invoke.mockImplementation(async () => ({
      ...created({
        title: '营收复盘',
        target_skill: 'skill-test',
        description: '',
        mcp_refs: [action],
        knowledge_refs: [],
      }).session,
      status: 'running',
    }))
  })

  afterEach(cleanup)

  it('does not request an invocation when saving an empty-context draft', async () => {
    renderNewSkill()

    fireEvent.change(await screen.findByLabelText('Skill 名称'), {
      target: { value: '空白草稿' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存草稿' }))

    await waitFor(() => expect(apiMocks.createSkill).toHaveBeenCalledOnce())
    expect(apiMocks.invoke).not.toHaveBeenCalled()
  })

  it('explicitly invokes generation after saving a configured draft', async () => {
    renderNewSkill()

    fireEvent.change(await screen.findByLabelText('Skill 名称'), {
      target: { value: '营收复盘' },
    })
    fireEvent.click(screen.getByText('添加 Action'))
    fireEvent.click(screen.getByRole('checkbox', { name: '查询订单' }))
    fireEvent.click(screen.getByRole('button', { name: '保存并开始生成' }))

    await waitFor(() => expect(apiMocks.invoke).toHaveBeenCalledOnce())
    expect(apiMocks.invoke.mock.calls[0][0]).toBe('session-1')
  })
})
