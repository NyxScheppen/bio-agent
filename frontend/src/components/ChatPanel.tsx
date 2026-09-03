import { useState, type FormEvent } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useChatStore } from '../stores/chatStore'

export default function ChatPanel() {
  const [input, setInput] = useState('')
  const messages = useChatStore((s) => s.messages)
  const status = useChatStore((s) => s.status)
  const send = useChatStore((s) => s.send)

  const onSubmit = (e: FormEvent): void => {
    e.preventDefault()
    const text = input.trim()
    if (!text || status === 'streaming') return
    setInput('')
    void send(text)
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="flex-1 overflow-y-auto space-y-2 p-4 min-h-0">
        {messages.map((m, i) => (
          <div key={i} className={m.role === 'user' ? 'text-right' : 'text-left'}>
            <div
              className={
                m.role === 'user'
                  ? 'inline-block rounded-lg px-3 py-2 bg-blue-600 text-white'
                  : 'inline-block max-w-full rounded-lg px-3 py-2 bg-gray-100 text-gray-900 text-sm markdown'
              }
            >
              {m.role === 'user' ? (
                m.content
              ) : (
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
              )}
            </div>
          </div>
        ))}
        {messages.length === 0 && <p className="text-sm text-gray-400">问点什么，比如：帮我做 DGE 分析</p>}
      </div>
      <form onSubmit={onSubmit} className="p-4 border-t">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="输入分析需求…"
          disabled={status === 'streaming'}
          className="w-full border rounded px-3 py-2 text-sm"
        />
      </form>
    </div>
  )
}
