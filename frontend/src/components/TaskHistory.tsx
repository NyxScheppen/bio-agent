import { useEffect } from 'react'
import { useTaskStore } from '../stores/taskStore'

export default function TaskHistory() {
  const tasks = useTaskStore((s) => s.tasks)
  const current = useTaskStore((s) => s.current)
  const refresh = useTaskStore((s) => s.refresh)
  const open = useTaskStore((s) => s.open)

  useEffect(() => {
    void refresh().catch(() => {})
  }, [refresh])

  return (
    <div className="p-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-gray-500">
            <th className="py-1">消息</th>
            <th className="py-1">状态</th>
            <th className="py-1">时间</th>
          </tr>
        </thead>
        <tbody>
          {tasks.map((t) => (
            <tr key={t.id} onClick={() => void open(t.id).catch(() => {})} className="cursor-pointer hover:bg-gray-50">
              <td className="py-1 pr-2 truncate max-w-[200px]">{t.userMessage}</td>
              <td className="py-1 pr-2">{t.status}</td>
              <td className="py-1">{new Date(t.createdAt * 1000).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {current?.status === 'failed' && (
        <div className="mt-2 text-sm text-red-600">失败原因：{current.error ?? '未知'}</div>
      )}
    </div>
  )
}
