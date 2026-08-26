import type { ExecutedStep, Step } from '../types'

interface Props {
  plan: Step[]
  steps: ExecutedStep[]
  failed: boolean
}

export default function StepList({ plan, steps, failed }: Props) {
  const doneTools = new Set(steps.map((s) => s.tool))
  return (
    <ol className="space-y-2 p-4">
      {plan.map((s, i) => {
        const done = doneTools.has(s.tool)
        const status: 'done' | 'pending' | 'failed' = failed ? 'failed' : done ? 'done' : 'pending'
        const cls =
          status === 'done' ? 'text-green-600' : status === 'failed' ? 'text-red-600' : 'text-gray-400'
        const icon = status === 'done' ? '✓' : status === 'failed' ? '✗' : '○'
        return (
          <li key={`${s.tool}-${i}`} className="flex items-center gap-2 text-sm">
            <span className={cls}>{icon}</span>
            <span>{s.tool}</span>
          </li>
        )
      })}
      {plan.length === 0 && <li className="text-sm text-gray-400">等待规划…</li>}
    </ol>
  )
}
