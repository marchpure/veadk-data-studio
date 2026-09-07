// @vitest-environment jsdom

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { SkillProgress } from './SkillProgress'

afterEach(cleanup)

describe('SkillProgress', () => {
  it('shows four steps and marks completed work', () => {
    render(<SkillProgress current={3} />)

    expect(screen.getByRole('navigation', { name: 'Skill 创建步骤' })).toBeTruthy()
    expect(screen.getByText('1. 定义目标')).toBeTruthy()
    expect(screen.getByText('2. 选择能力')).toBeTruthy()
    expect(screen.getByText('3. 生成 Skill')).toBeTruthy()
    expect(screen.getByText('4. 开始使用')).toBeTruthy()
    expect(document.querySelectorAll('.dw-skill-progress-step.done')).toHaveLength(2)
    expect(document.querySelector('.dw-skill-progress-step.active')?.textContent).toContain('3. 生成 Skill')
  })
})
