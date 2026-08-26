import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import StepList from './StepList'

describe('StepList', () => {
  it('失败任务时已完成步骤仍标 ✓，未执行步骤标 ✗', () => {
    render(
      <StepList
        plan={[
          { tool: 'a', args: {} },
          { tool: 'b', args: {} },
          { tool: 'c', args: {} },
        ]}
        steps={[{ tool: 'a', status: 'completed', result: {} }]}
        failed
      />,
    )
    const items = screen.getAllByRole('listitem')
    expect(items[0].textContent).toContain('✓')
    expect(items[1].textContent).toContain('✗')
    expect(items[2].textContent).toContain('✗')
  })
})
