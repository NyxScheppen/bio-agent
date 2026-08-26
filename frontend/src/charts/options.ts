import type { EChartsOption } from 'echarts'
import type { BarplotResult, BoxplotResult, KmCurveResult, NetworkResult, VolcanoResult } from '../types'

// 五种图表的 option 纯函数：同输入必同输出，无副作用，单测不碰 DOM

export function boxplotOption(data: BoxplotResult): EChartsOption {
  const categories = Object.keys(data.samples)
  const seriesData: number[][] = categories.map((cat) => {
    const sorted = [...data.samples[cat]].sort((a, b) => a - b)
    const n = sorted.length
    return [
      sorted[0],
      sorted[Math.floor(n * 0.25)],
      sorted[Math.floor(n * 0.5)],
      sorted[Math.floor(n * 0.75)],
      sorted[n - 1],
    ]
  })
  return {
    title: { text: data.gene, left: 'center' },
    tooltip: { trigger: 'item' },
    xAxis: { type: 'category', data: categories },
    yAxis: { type: 'value', name: '表达量' },
    series: [{ type: 'boxplot', data: seriesData }],
  }
}

export function volcanoOption(data: VolcanoResult): EChartsOption {
  const seriesData = data.genes.map((g) => ({
    value: [g.logFC, -Math.log10(g.p_value)] as [number, number],
    itemStyle: { color: g.adj_p_value < 0.05 ? '#e74c3c' : '#95a5a6' },
  }))
  return {
    title: { text: '火山图', left: 'center' },
    tooltip: { trigger: 'item' },
    xAxis: { type: 'value', name: 'logFC' },
    yAxis: { type: 'value', name: '-log10(p)' },
    series: [{ type: 'scatter', data: seriesData }],
  }
}

export function barplotOption(data: BarplotResult): EChartsOption {
  const rows = [...data.go, ...data.kegg]
  const terms = rows.map((r) => r.term).reverse()
  const values = rows.map((r) => -Math.log10(r.p_value)).reverse()
  return {
    title: { text: '富集分析（-log10 p）', left: 'center' },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'value', name: '-log10(p)' },
    yAxis: { type: 'category', data: terms },
    series: [{ type: 'bar', data: values }],
  }
}

export function networkOption(data: NetworkResult): EChartsOption {
  const nodes = data.nodes.map((n) => ({
    id: n.id,
    name: n.id,
    symbolSize: Math.max(5, Math.min(40, n.degree * 4)),
  }))
  const links = data.edges.map((e) => ({ source: e.source, target: e.target }))
  return {
    title: { text: 'PPI 网络', left: 'center' },
    tooltip: { trigger: 'item' },
    series: [
      {
        type: 'graph',
        layout: 'force',
        roam: true,
        data: nodes,
        links,
        force: { repulsion: 200, edgeLength: 50 },
      },
    ],
  }
}

export function kmCurveOption(data: KmCurveResult): EChartsOption {
  const series = data.km_curves.map((curve) => ({
    name: curve.group,
    type: 'line' as const,
    step: 'end' as const,
    data: curve.time.map((t, i) => [t, curve.survival[i]] as [number, number]),
  }))
  return {
    title: { text: 'KM 生存曲线', left: 'center' },
    tooltip: { trigger: 'axis' },
    legend: { data: data.km_curves.map((c) => c.group) },
    xAxis: { type: 'value', name: '时间' },
    yAxis: { type: 'value', name: '生存率', min: 0, max: 1 },
    series,
  }
}
