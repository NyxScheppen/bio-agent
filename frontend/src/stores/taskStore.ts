import { create } from 'zustand'
import type { TaskDetail, TaskSummary } from '../types'
import * as client from '../api/client'

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
  },
}))
