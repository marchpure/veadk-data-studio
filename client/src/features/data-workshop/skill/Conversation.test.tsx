// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { Conversation } from './Conversation'
import type { SkillSession } from './types'

afterEach(cleanup)

function session(overrides: Partial<SkillSession> = {}): SkillSession {
  return {
    id: 'session-1',
    skill_id: 'skill-1',
    title: '初始会话',
    status: 'draft',
    context_refs: { mcp_refs: [], knowledge_refs: [] },
    messages: [],
    events: [],
    ...overrides,
  }
}

function renderConversation(value: SkillSession, onSend = vi.fn()) {
  return {
    onSend,
    ...render(
      <Conversation
        session={value}
        onSend={onSend}
        onCancel={vi.fn()}
        onRetry={vi.fn()}
      />,
    ),
  }
}

describe('Conversation', () => {
  it('guides an empty draft to add context without invoking generation', () => {
    const onSend = vi.fn().mockResolvedValue(undefined)
    renderConversation(session(), onSend)

    fireEvent.change(screen.getByLabelText('Skill 消息'), {
      target: { value: '你可以做什么' },
    })
    fireEvent.click(screen.getByRole('button', { name: '开始生成' }))

    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByText('请先添加至少一个 Action 或知识资源，再开始生成。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '添加 Action' })).toBeTruthy()
    expect(screen.getByRole('button', { name: '添加知识' })).toBeTruthy()
  })

  it('keeps protocol events collapsed and presents service auth as an admin issue', () => {
    renderConversation(session({
      status: 'blocked_auth',
      events: [
        {
          id: 'event-1',
          type: 'session_created',
          message: '会话已创建',
        },
        {
          id: 'event-2',
          type: 'invocation_started',
          message: 'W5 已接收任务',
          code: 'BLOCKED_AUTH',
        },
      ],
    }))

    expect(screen.getByText('生成服务认证异常，请联系管理员')).toBeTruthy()
    expect(screen.queryByText('OAuth')).toBeNull()
    const technicalDetails = screen.getByText('技术详情').closest('details')
    expect(technicalDetails?.open).toBe(false)
    expect(technicalDetails?.textContent).toContain('session_created')
    expect(technicalDetails?.textContent).toContain('W5 已接收任务')
    expect(document.body.textContent?.replace(technicalDetails?.textContent || '', '')).not.toContain('session_created')
    expect(document.body.textContent?.replace(technicalDetails?.textContent || '', '')).not.toContain('W5 已接收任务')
    expect(screen.getByRole('button', { name: '开始生成' })).toBeTruthy()
  })

  it.each([
    ['draft', [], '草稿已保存'],
    ['running', [{ id: 'started', type: 'invocation_started' }], '开始生成'],
    ['running', [{ id: 'validation', type: 'validation' }], '校验中'],
    ['ready', [{ id: 'artifact', type: 'artifact.created' }], '生成完成'],
    ['validation_failed', [{ id: 'failed', type: 'validation_failed' }], '校验未通过'],
  ] as const)('shows the %s user phase as %s', (status, events, expected) => {
    renderConversation(session({
      status,
      context_refs: {
        mcp_refs: [{
          id: 'action',
          kind: 'mcp_action',
          name: '查询',
          source: 'OpenConnector',
          metadata: {},
        }],
        knowledge_refs: [],
      },
      events: [...events],
    }))

    const progress = screen.getByText('生成进度').closest('section') as HTMLElement
    expect(within(progress).getByText(expected)).toBeTruthy()
  })

  it('shows the ready terminal state without presenting historical retry failures as current', () => {
    renderConversation(session({
      status: 'ready',
      context_refs: {
        mcp_refs: [{
          id: 'action',
          kind: 'mcp_action',
          name: '查询',
          source: 'OpenConnector',
          metadata: {},
        }],
        knowledge_refs: [],
      },
      events: [
        { id: 'old-failure', type: 'retryable', message: 'historical failure' },
        { id: 'artifact', type: 'artifact.created', message: 'artifact ready' },
      ],
    }))

    const progress = screen.getByText('生成进度').closest('section') as HTMLElement
    expect(within(progress).getByText('生成完成')).toBeTruthy()
    expect(within(progress).queryByText('生成失败')).toBeNull()
  })
})
