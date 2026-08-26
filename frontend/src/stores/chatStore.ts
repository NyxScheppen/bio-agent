import { create } from 'zustand'
import type { AgentState, Message } from '../types'
import { readSSE } from '../hooks/useSSE'

interface ChatState {
  messages: Message[]                 // 用户/助手消息
  currentState: AgentState | null     // 最新 SSE 快照
  status: 'idle' | 'streaming' | 'done' | 'error'
  send: (message: string) => Promise<void>  // POST /chat，逐帧更新 currentState
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  currentState: null,
  status: 'idle',

  send: async (message: string): Promise<void> => {
    set((s) => ({
      messages: [...s.messages, { role: 'user' as const, content: message }],
      status: 'streaming' as const,
      currentState: { query: message },
    }))
    try {
      const resp = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('响应无 body')
      const reader = resp.body.getReader()
      await readSSE(reader, (snapshot) => {
        set({
          currentState: snapshot,
          status: snapshot.report != null ? ('done' as const) : ('streaming' as const),
        })
      })
      set({ status: 'done' })
    } catch (err) {
      set({ status: 'error' })
      throw err
    }
  },
}))
