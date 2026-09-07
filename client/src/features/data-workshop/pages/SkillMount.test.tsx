// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

import { SkillMount } from './SkillMount'
import type { SkillContextRef, SkillSession, WorkshopSkill } from '../skill/types'

const apiMocks = vi.hoisted(() => ({
  catalog: vi.fn(),
  listSkills: vi.fn(),
  listSessions: vi.fn(),
  revisions: vi.fn(),
  getSession: vi.fn(),
  createSession: vi.fn(),
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
    listSessions: apiMocks.listSessions,
    revisions: apiMocks.revisions,
    getSession: apiMocks.getSession,
    createSession: apiMocks.createSession,
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

function skillFixture(): WorkshopSkill {
  return {
    id: 'skill-1',
    title: '营收复盘',
    target_skill: 'revenue-review',
    description: '汇总订单和知识库',
    status: 'ready',
    context_refs: { mcp_refs: [action], knowledge_refs: [] },
  }
}

function sessionFixture(overrides: Partial<SkillSession> = {}): SkillSession {
  return {
    id: 'session-1',
    skill_id: 'skill-1',
    title: '初始会话',
    status: 'draft',
    context_refs: { mcp_refs: [action], knowledge_refs: [] },
    messages: [],
    events: [],
    ...overrides,
  }
}

function renderExistingSkill(path = '/skill') {
  return render(
    <MemoryRouter initialEntries={[path]}>
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
    apiMocks.listSessions.mockResolvedValue({ items: [], total: 0 })
    apiMocks.revisions.mockResolvedValue({ items: [], total: 0 })
    apiMocks.getSession.mockResolvedValue(sessionFixture())
    apiMocks.createSession.mockResolvedValue(sessionFixture({ id: 'session-new' }))
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

describe('SkillMount bounded loading states', () => {
  beforeEach(() => {
    Object.values(apiMocks).forEach(mock => mock.mockReset())
    apiMocks.listSkills.mockResolvedValue({ items: [skillFixture()], total: 1 })
    apiMocks.listSessions.mockResolvedValue({ items: [], total: 0 })
    apiMocks.revisions.mockResolvedValue({ items: [], total: 0 })
    apiMocks.getSession.mockResolvedValue(sessionFixture())
    apiMocks.catalog.mockResolvedValue({
      backend: 'REAL',
      w5_configured: true,
      connections: [{ id: 'orders', name: '订单库', provider: 'internal', actions: [action] }],
      knowledge_refs: [],
    })
  })

  afterEach(cleanup)

  it('shows an existing Skill even when catalog remains pending', async () => {
    apiMocks.catalog.mockImplementation(() => new Promise(() => undefined))
    renderExistingSkill()
    expect(await screen.findByRole('button', { name: /营收复盘/ })).toBeTruthy()
    expect(screen.queryByText('正在打开 Skill 工作台')).not.toBeTruthy()
  })

  it('keeps the list available and exposes a catalog-local error', async () => {
    apiMocks.catalog.mockRejectedValue(new Error('目录不可用'))
    renderExistingSkill()
    expect(await screen.findByRole('button', { name: /营收复盘/ })).toBeTruthy()
    expect(await screen.findByText('目录不可用')).toBeTruthy()
  })

  it('settles list failure into an error with retry', async () => {
    apiMocks.listSkills.mockRejectedValue(new Error('列表不可用'))
    renderExistingSkill()
    expect(await screen.findByText('Skill 暂时不可用')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: '重试' }).length).toBeGreaterThan(0)
  })

  it('settles an empty list into a stable new Skill state', async () => {
    apiMocks.listSkills.mockResolvedValue({ items: [], total: 0 })
    renderExistingSkill()
    expect(await screen.findByText('把数据能力变成可复用的 Skill')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: '新建 Skill' }).length).toBeGreaterThan(0)
  })

  it('recovers an invalid skill query to the first available Skill', async () => {
    renderExistingSkill('/skill?skillId=missing')
    expect(await screen.findByRole('button', { name: /营收复盘/ })).toBeTruthy()
    await waitFor(() => expect(apiMocks.listSessions).toHaveBeenCalledWith('skill-1', expect.anything()))
  })

  it('shows a create-session action when the selected Skill has no sessions', async () => {
    renderExistingSkill('/skill?skillId=skill-1')
    expect(await screen.findByText('还没有会话')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '新建会话' }))
    await waitFor(() => expect(apiMocks.createSession).toHaveBeenCalledWith('skill-1'))
  })

  it('does not update the unmounted component after requests settle', async () => {
    let resolveSkills: ((value: { items: WorkshopSkill[]; total: number }) => void) | undefined
    apiMocks.listSkills.mockImplementation(() => new Promise(resolve => { resolveSkills = resolve }))
    const { unmount } = renderExistingSkill()
    unmount()
    resolveSkills?.({ items: [skillFixture()], total: 1 })
    await Promise.resolve()
    expect(screen.queryByText('营收复盘')).not.toBeTruthy()
  })
})
