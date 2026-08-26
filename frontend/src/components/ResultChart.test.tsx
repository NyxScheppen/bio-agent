import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ResultChart from './ResultChart'
import type { ExecutedStep, ToolMeta } from '../types'

vi.mock('../charts/ECharts', () => ({
  default: ({ option }: { option: Record<string, unknown> }) => {
    const series = option.series as Array<{ type?: string }>
    return <div data-testid="chart-type">{series[0]?.type ?? 'none'}</div>
  },
}))

describe('ResultChart 分发', () => {
  const tools: ToolMeta[] = [
    { name: 'limma_dge', description: '', category: 'dge', runtime: 'python', input_schema: {}, frontend: { result_type: 'volcano' } },
  ]

  it('limma_dge → volcano → scatter', () => {
    const step: ExecutedStep = {
      tool: 'limma_dge',
      status: 'completed',
      result: { genes: [{ gene: 'a', logFC: 1, p_value: 0.01, adj_p_value: 0.01 }] },
    }
    render(<ResultChart step={step} tools={tools} />)
    expect(screen.getByTestId('chart-type').textContent).toBe('scatter')
  })

  it('未知 result_type → 展示 JSON 不崩', () => {
    const step: ExecutedStep = { tool: 'unknown_tool', status: 'completed', result: { foo: 1 } }
    const { container } = render(<ResultChart step={step} tools={[]} />)
    expect(container.querySelector('pre')?.textContent).toContain('foo')
  })
})
