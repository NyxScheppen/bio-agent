import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTaskStore } from './taskStore'
import { useChatStore } from './chatStore'
import * as client from '../api/client'

vi.mock('../api/client', () => ({
  listTasks: vi.fn(),
  getTask: vi.fn(),
}))

describe('taskStore', () => {
  beforeEach(() => {
    useTaskStore.setState({ tasks: [], current: null, loading: false })
    useChatStore.setState({ messages: [], currentState: null, status: 'idle' })
    vi.mocked(client.getTask).mockReset()
  })

  it('open 取回任务并把内容回填主视图与对话', async () => {
    vi.mocked(client.getTask).mockResolvedValue({
      id: 't1',
      userMessage: 'hi',
      status: 'completed',
      createdAt: 1,
      updatedAt: 2,
      plan: [{ tool: 'dge', args: {} }],
      steps: [{ tool: 'dge', status: 'completed', result: { x: 1 } }],
      report: '# r',
      error: null,
    })

    await useTaskStore.getState().open('t1')

    expect(useTaskStore.getState().current?.id).toBe('t1')
    const c = useChatStore.getState()
    expect(c.currentState?.report).toBe('# r')
    expect(c.currentState?.plan).toHaveLength(1)
    expect(c.messages).toEqual([
      { role: 'user', content: 'hi' },
      { role: 'assistant', content: '# r' },
    ])
    expect(c.status).toBe('done')
  })

  it('open 失败任务 → 主视图 status error', async () => {
    vi.mocked(client.getTask).mockResolvedValue({
      id: 't2',
      userMessage: 'x',
      status: 'failed',
      createdAt: 1,
      updatedAt: 2,
      plan: [],
      steps: [],
      report: '',
      error: 'boom',
    })

    await useTaskStore.getState().open('t2')

    expect(useTaskStore.getState().current?.error).toBe('boom')
    expect(useChatStore.getState().status).toBe('error')
  })
})
