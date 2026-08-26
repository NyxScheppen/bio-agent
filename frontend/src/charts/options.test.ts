import { describe, expect, it } from 'vitest'
import {
  barplotOption,
  boxplotOption,
  kmCurveOption,
  networkOption,
  volcanoOption,
} from './options'
import type { BarplotResult, BoxplotResult, KmCurveResult, NetworkResult, VolcanoResult } from '../types'

type Series = { type?: string; step?: string; data?: unknown[] }

function seriesOf(option: { series?: unknown }): Series[] {
  return option.series as Series[]
}

describe('options.ts 纯函数', () => {
  it('boxplotOption 返回 boxplot series', () => {
    const data: BoxplotResult = {
      gene: 'TP53',
      samples: { A: [1, 2, 3, 4, 5], B: [6, 7, 8, 9, 10] },
      summary: {
        A: { n: 5, mean: 3, median: 3, sd: 1 },
        B: { n: 5, mean: 8, median: 8, sd: 1 },
      },
      p_value: 0.01,
    }
    const option = boxplotOption(data)
    expect(seriesOf(option)[0].type).toBe('boxplot')
    expect(option.xAxis).toBeDefined()
    expect(option.yAxis).toBeDefined()
  })

  it('volcanoOption 返回 scatter，空 genes 不抛且空 series', () => {
    const empty: VolcanoResult = { genes: [] }
    const option = volcanoOption(empty)
    expect(seriesOf(option)[0].type).toBe('scatter')
    expect(seriesOf(option)[0].data).toEqual([])
  })

  it('barplotOption 返回 bar', () => {
    const data: BarplotResult = {
      go: [{ id: 'GO:1', term: 'a', p_value: 0.01, adj_p_value: 0.05, gene_count: 3 }],
      kegg: [{ id: 'hsa:1', term: 'b', p_value: 0.02, adj_p_value: 0.05, gene_count: 2 }],
    }
    expect(seriesOf(barplotOption(data))[0].type).toBe('bar')
  })

  it('networkOption 返回 graph', () => {
    const data: NetworkResult = {
      nodes: [{ id: 'a', degree: 1 }],
      edges: [{ source: 'a', target: 'b', score: 0.5 }],
    }
    expect(seriesOf(networkOption(data))[0].type).toBe('graph')
  })

  it('kmCurveOption 返回 line 且 step=end', () => {
    const data: KmCurveResult = {
      km_curves: [{ group: 'g', time: [0, 1, 2], survival: [1, 0.8, 0.6] }],
      logrank_p: 0.1,
      cox_hr: 0.5,
      cox_p: 0.2,
    }
    const series = seriesOf(kmCurveOption(data))[0]
    expect(series.type).toBe('line')
    expect(series.step).toBe('end')
  })
})
