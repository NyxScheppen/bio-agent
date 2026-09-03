import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import ChatPanel from './ChatPanel'
import { useChatStore } from '../stores/chatStore'

describe('ChatPanel', () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [], conversationId: 'c', currentState: null, status: 'idle' })
  })

  it('助手 markdown 报告渲染在对话中', () => {
    useChatStore.setState({
      messages: [{ role: 'assistant', content: '# 分析报告\n\n[KEGG](https://kegg.jp)' }],
    })
    render(<ChatPanel />)
    expect(screen.getByRole('heading', { name: '分析报告' })).toBeInTheDocument()
    expect(screen.getByText('KEGG')).toBeInTheDocument()
  })
})
