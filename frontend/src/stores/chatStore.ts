import { create } from 'zustand'
import type { AgentState, Message } from '../types'
import { readSSE } from '../hooks/useSSE'

interface ChatState {
  messages: Message[]                 // 用户/助手消息（完整多轮对话）
  conversationId: string              // 对话 id，随消息发给后端
  currentState: AgentState | null     // 最新 SSE 快照（驱动 步骤/结果 面板）
  status: 'idle' | 'streaming' | 'done' | 'error'
  send: (message: string) => Promise<void>
  reset: () => void                   // 新对话：清空 + 新 conversationId
}

export const useChatStore = create<ChatState>((set, get) => ({
  messages: [],
  conversationId: crypto.randomUUID(),
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
        body: JSON.stringify({ message, conversation_id: get().conversationId }),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('响应无 body')
      const reader = resp.body.getReader()
      let lastReport = ''
      await readSSE(reader, (snapshot) => {
        if (snapshot.report != null) lastReport = snapshot.report
        set({
          currentState: snapshot,
          status: snapshot.report != null ? ('done' as const) : ('streaming' as const),
        })
      })
      set((s) => ({
        status: 'done',
        messages: lastReport
          ? [...s.messages, { role: 'assistant' as const, content: lastReport }]
          : s.messages,
      }))
    } catch (err) {
      set({ status: 'error' })
      throw err
    }
  },

  reset: (): void =>
    set({ messages: [], conversationId: crypto.randomUUID(), currentState: null, status: 'idle' }),
}))
