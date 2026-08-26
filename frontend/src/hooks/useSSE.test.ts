import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useSSE } from './useSSE'

function fakeStream(chunks: string[]) {
  let i = 0
  const cancel = vi.fn(async () => {})
  const read = vi.fn(async () => {
    if (i >= chunks.length) return { done: true, value: undefined }
    return { done: false, value: new TextEncoder().encode(chunks[i++]) }
  })
  const body = { getReader: () => ({ read, cancel }) }
  return { body, read, cancel }
}

describe('useSSE', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('逐帧 onEvent + done 结束', async () => {
    const { body } = fakeStream([
      'data: {"query":"hi"}\n\n',
      'data: {"plan":[]}\n\n',
      'data: {"done":true}\n\n',
    ])
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body }))

    const onEvent = vi.fn()
    const { result } = renderHook(() => useSSE(onEvent))

    await act(async () => {
      await result.current.run('/chat', { message: 'hi' })
    })

    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent).toHaveBeenNthCalledWith(1, { query: 'hi' })
    expect(onEvent).toHaveBeenNthCalledWith(2, { plan: [] })
    expect(result.current.error).toBeNull()
  })

  it('非 200 置 error 并 reject', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    const { result } = renderHook(() => useSSE(() => {}))

    await act(async () => {
      await expect(result.current.run('/chat', {})).rejects.toThrow('HTTP 500')
    })
    expect(result.current.error).toBe('HTTP 500')
  })

  it('stop() 中止 reader', async () => {
    let resolveRead: (() => void) | null = null
    const cancel = vi.fn(() => {
      resolveRead?.()
      return Promise.resolve()
    })
    const read = vi.fn(
      () =>
        new Promise<{ done: boolean; value?: Uint8Array }>((resolve) => {
          resolveRead = () => resolve({ done: true, value: undefined })
        }),
    )
    const body = { getReader: () => ({ read, cancel }) }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, body }))

    const { result } = renderHook(() => useSSE(() => {}))

    await act(async () => {
      const p = result.current.run('/chat', {})
      await new Promise((r) => setTimeout(r, 0))
      result.current.stop()
      await p
    })

    expect(cancel).toHaveBeenCalledTimes(1)
  })
})
