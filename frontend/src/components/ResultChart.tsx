import type { EChartsOption } from 'echarts'
import type {
  BarplotResult,
  BoxplotResult,
  ExecutedStep,
  KmCurveResult,
  NetworkResult,
  ToolMeta,
  VolcanoResult,
} from '../types'
import {
  barplotOption,
  boxplotOption,
  kmCurveOption,
  networkOption,
  volcanoOption,
} from '../charts/options'
import ECharts from '../charts/ECharts'

interface Props {
  step: ExecutedStep
  tools: ToolMeta[]
}

function toResultType(tool: string, tools: ToolMeta[]): string | undefined {
  return tools.find((t) => t.name === tool)?.frontend.result_type
}

function toOption(resultType: string | undefined, result: unknown): EChartsOption | null {
  switch (resultType) {
    case 'boxplot':
      return boxplotOption(result as BoxplotResult)
    case 'volcano':
      return volcanoOption(result as VolcanoResult)
    case 'barplot':
      return barplotOption(result as BarplotResult)
    case 'network':
      return networkOption(result as NetworkResult)
    case 'km_curve':
      return kmCurveOption(result as KmCurveResult)
    default:
      return null
  }
}

export default function ResultChart({ step, tools }: Props) {
  const option = toOption(toResultType(step.tool, tools), step.result)

  if (option) {
    return <ECharts option={option} />
  }
  return <pre className="text-xs overflow-auto max-h-80 bg-gray-50 p-2 rounded">{JSON.stringify(step.result, null, 2)}</pre>
}
