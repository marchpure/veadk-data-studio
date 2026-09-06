// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { NewSkill } from './NewSkill'

afterEach(cleanup)

describe('NewSkill', () => {
  it('saves an empty-context draft but does not allow generation', () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)

    render(<NewSkill catalog={null} creating={false} onCreate={onCreate} />)

    fireEvent.change(screen.getByLabelText('Skill 名称'), {
      target: { value: '周度营收复盘' },
    })

    expect(screen.queryByText('Target Skill')).toBeNull()
    expect(screen.queryByText('New Skill')).toBeNull()
    const saveDraft = screen.getByRole('button', { name: '保存草稿' })
    const saveAndGenerate = screen.getByRole('button', { name: '保存并开始生成' })
    expect((saveDraft as HTMLButtonElement).disabled).toBe(false)
    expect((saveAndGenerate as HTMLButtonElement).disabled).toBe(true)

    fireEvent.click(saveDraft)

    expect(onCreate).toHaveBeenCalledOnce()
    expect(onCreate.mock.calls[0][1]).toBe('draft')
    expect(onCreate.mock.calls[0][0].target_skill).toMatch(/^skill-[a-z0-9-]+$/)
  })

  it('allows generation only after selecting a visible context item', () => {
    const onCreate = vi.fn().mockResolvedValue(undefined)
    const action = {
      id: 'orders.list',
      kind: 'mcp_action' as const,
      name: '查询订单',
      source: 'OpenConnector' as const,
      connection_id: 'orders',
      metadata: {},
    }

    render(
      <NewSkill
        catalog={{
          backend: 'REAL',
          w5_configured: true,
          connections: [{ id: 'orders', name: '订单库', provider: 'internal', actions: [action] }],
          knowledge_refs: [],
        }}
        creating={false}
        onCreate={onCreate}
      />,
    )

    fireEvent.change(screen.getByLabelText('Skill 名称'), {
      target: { value: 'Revenue Review' },
    })
    fireEvent.click(screen.getByText('添加 Action'))
    fireEvent.click(screen.getByRole('checkbox', { name: '查询订单' }))

    const generate = screen.getByRole('button', { name: '保存并开始生成' })
    expect((generate as HTMLButtonElement).disabled).toBe(false)
    fireEvent.click(generate)

    expect(onCreate).toHaveBeenCalledOnce()
    expect(onCreate.mock.calls[0][1]).toBe('generate')
    expect(onCreate.mock.calls[0][0].mcp_refs).toEqual([action])
  })
})
