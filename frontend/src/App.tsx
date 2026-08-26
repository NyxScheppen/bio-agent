import { useEffect, useState } from 'react'
import ChatPanel from './components/ChatPanel'
import StepList from './components/StepList'
import ResultChart from './components/ResultChart'
import TaskHistory from './components/TaskHistory'
import FileUpload from './components/FileUpload'
import { useChatStore } from './stores/chatStore'
import { listTools } from './api/client'
import type { ToolMeta } from './types'

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

  return (
    <div className="min-h-screen p-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-1 border rounded-lg flex flex-col">
        <h2 className="font-semibold p-4 pb-0">对话</h2>
        <ChatPanel />
      </div>
      <div className="lg:col-span-1 border rounded-lg">
        <h2 className="font-semibold p-4 pb-0">步骤</h2>
        <StepList plan={plan} steps={steps} failed={failed} />
      </div>
      <div className="lg:col-span-1 border rounded-lg p-4 space-y-4">
        <h2 className="font-semibold">结果</h2>
        {steps.map((s, i) => (
          <div key={i}>
            <div className="text-sm font-medium text-gray-700">{s.tool}</div>
            <ResultChart step={s} tools={tools} />
          </div>
        ))}
        {steps.length === 0 && <p className="text-sm text-gray-400">暂无结果</p>}
        {currentState?.report && (
          <pre className="text-sm whitespace-pre-wrap bg-gray-50 p-3 rounded">{currentState.report}</pre>
        )}
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
