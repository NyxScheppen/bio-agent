import { create } from 'zustand'
import type { TaskDetail, TaskSummary } from '../types'
import * as client from '../api/client'
import { useChatStore } from './chatStore'

interface TaskState {
  tasks: TaskSummary[]
  current: TaskDetail | null
  loading: boolean
  refresh: () => Promise<void>
  open: (id: string) => Promise<void>
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: [],
  current: null,
  loading: false,

  refresh: async (): Promise<void> => {
    set({ loading: true })
    try {
      const tasks = await client.listTasks()
      set({ tasks, loading: false })
    } catch (err) {
      set({ loading: false })
      throw err
    }
  },

  open: async (id: string): Promise<void> => {
    const detail = await client.getTask(id)
    set({ current: detail })
    // 回看：把历史任务内容回填主视图（复用 StepList/ResultChart/report 渲染）
    useChatStore.setState({
      currentState: { plan: detail.plan, steps: detail.steps, report: detail.report },
      status: detail.status === 'failed' ? 'error' : 'done',
    })
  },
}))
