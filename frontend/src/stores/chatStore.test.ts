import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from './chatStore'

function fakeStream(chunks: string[]) {
  let i = 0
  const cancel = vi.fn(async () => {})
  const read = vi.fn(async () => {
    if (i >= chunks.length) return { done: true, value: undefined }
    return { done: false, value: new TextEncoder().encode(chunks[i++]) }
  })
  return { body: { getReader: () => ({ read, cancel }) } }
}

describe('chatStore', () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [], currentState: null, status: 'idle' })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('send 入消息、快照随帧更新、report 后 done', async () => {
    const { body } = fakeStream([
      'data: {"query":"hi"}\n\n',
      'data: {"query":"hi","plan":[{"tool":"dge","args":{}}]}\n\n',
      'data: {"query":"hi","plan":[{"tool":"dge","args":{}}],"report":"# r"}\n\n',
      'data: {"done":true}\n\n',
    ])
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body }))

    await useChatStore.getState().send('hi')

    const s = useChatStore.getState()
    expect(s.messages).toEqual([{ role: 'user', content: 'hi' }])
    expect(s.currentState?.plan).toHaveLength(1)
    expect(s.currentState?.report).toBe('# r')
    expect(s.status).toBe('done')
  })

  it('error 帧 → status error', async () => {
    const { body } = fakeStream(['data: {"error":"boom"}\n\n'])
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body }))

    await expect(useChatStore.getState().send('hi')).rejects.toThrow('boom')
    expect(useChatStore.getState().status).toBe('error')
  })
})
