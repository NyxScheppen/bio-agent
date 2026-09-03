import { useEffect, useState } from 'react'
import ChatPanel from './components/ChatPanel'
import StepList from './components/StepList'
import ResultChart from './components/ResultChart'
import TaskHistory from './components/TaskHistory'
import FileUpload from './components/FileUpload'
import { useChatStore } from './stores/chatStore'
import { listTools } from './api/client'
import type { ExecutedStep, ToolMeta } from './types'

const CHART_RESULT_TYPES = new Set(['boxplot', 'volcano', 'barplot', 'network', 'km_curve'])

function isChartStep(step: ExecutedStep, tools: ToolMeta[]): boolean {
  const type = tools.find((t) => t.name === step.tool)?.frontend.result_type
  return type != null && CHART_RESULT_TYPES.has(type)
}

export default function App() {
  const [tools, setTools] = useState<ToolMeta[]>([])
  const currentState = useChatStore((s) => s.currentState)
  const status = useChatStore((s) => s.status)

  useEffect(() => {
    void listTools().then(setTools).catch(() => {})
  }, [])

  const plan = currentState?.plan ?? []
  const steps = currentState?.steps ?? []
  const failed = status === 'error'
  const chartSteps = steps.filter((s) => isChartStep(s, tools))

  return (
    <div className="min-h-screen p-4 grid grid-cols-1 lg:grid-cols-3 gap-4 items-start">
      <div className="lg:col-span-1 border rounded-lg flex flex-col h-[80vh]">
        <div className="flex items-center justify-between p-4 pb-0">
          <h2 className="font-semibold">对话</h2>
          <button
            onClick={() => useChatStore.getState().reset()}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            新对话
          </button>
        </div>
        <ChatPanel />
      </div>
      <div className="lg:col-span-1 border rounded-lg">
        <h2 className="font-semibold p-4 pb-0">步骤</h2>
        <StepList plan={plan} steps={steps} failed={failed} />
      </div>
      <div className="lg:col-span-1 border rounded-lg p-4 space-y-4">
        <h2 className="font-semibold">结果</h2>
        {chartSteps.map((s, i) => (
          <div key={i}>
            <div className="text-sm font-medium text-gray-700">{s.tool}</div>
            <ResultChart step={s} tools={tools} />
          </div>
        ))}
        {chartSteps.length === 0 && <p className="text-sm text-gray-400">暂无结果</p>}
      </div>
      <div className="lg:col-span-3 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="border rounded-lg">
          <h2 className="font-semibold p-4 pb-0">上传</h2>
          <FileUpload />
        </div>
        <div className="border rounded-lg">
          <h2 className="font-semibold p-4 pb-0">任务历史</h2>
          <TaskHistory />
        </div>
      </div>
    </div>
  )
}
