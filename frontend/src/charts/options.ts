import type { EChartsOption } from 'echarts'
import type { BarplotResult, BoxplotResult, KmCurveResult, NetworkResult, VolcanoResult } from '../types'

// 五种图表的 option 纯函数：同输入必同输出，无副作用，单测不碰 DOM

// 线性插值分位数（pandas/numpy 'linear' 默认），避免 floor 下标与后端 median 不一致
function quantile(sorted: number[], q: number): number {
  const pos = (sorted.length - 1) * q
  const lo = Math.floor(pos)
  const hi = Math.ceil(pos)
  if (lo === hi) return sorted[lo]
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo)
}

export function boxplotOption(data: BoxplotResult): EChartsOption {
  const categories = Object.keys(data.samples)
  const seriesData: number[][] = categories.map((cat) => {
    const sorted = [...data.samples[cat]].sort((a, b) => a - b)
    return [
      sorted[0],
      quantile(sorted, 0.25),
      data.summary[cat].median,
      quantile(sorted, 0.75),
      sorted[sorted.length - 1],
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
    value: [g.logFC, -Math.log10(Math.max(g.p_value, 1e-300))] as [number, number],
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
  const values = rows.map((r) => -Math.log10(Math.max(r.p_value, 1e-300))).reverse()
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
