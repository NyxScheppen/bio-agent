import { useRef, useState } from 'react'
import type { AgentState } from '../types'

type Reader = ReadableStreamDefaultReader<Uint8Array>

// 读流核心：逐帧解析 "data: {json}\n\n"。
//   done 帧  → resolve（正常结束）
//   error 帧 → reject（错误）
//   否则      → 整帧是完整状态快照，onEvent(snapshot)
// 供 useSSE hook 与 chatStore.send 复用，避免两处重复解析逻辑。
export async function readSSE(reader: Reader, onEvent: (snapshot: AgentState) => void): Promise<void> {
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let sep = buffer.indexOf('\n\n')
    while (sep !== -1) {
      const raw = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const payload = raw.startsWith('data: ') ? raw.slice(6) : raw
      const frame = JSON.parse(payload) as AgentState & { done?: boolean; error?: string }
      if (frame.done) return
      if (frame.error) {
        reader.cancel().catch(() => {})
        throw new Error(frame.error)
      }
      onEvent(frame)
      sep = buffer.indexOf('\n\n')
    }
  }
}

export function useSSE(onEvent: (snapshot: AgentState) => void): {
  run: (url: string, body: unknown) => Promise<void>
  stop: () => void
  error: string | null
} {
  const readerRef = useRef<Reader | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async (url: string, body: unknown): Promise<void> => {
    setError(null)
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      if (!resp.body) throw new Error('响应无 body')
      const reader = resp.body.getReader()
      readerRef.current = reader
      await readSSE(reader, onEvent)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    } finally {
      readerRef.current = null
    }
  }

  const stop = (): void => {
    readerRef.current?.cancel().catch(() => {})
  }

  return { run, stop, error }
}
