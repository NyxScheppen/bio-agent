import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import ChatPanel from './ChatPanel'
import { useChatStore } from '../stores/chatStore'

describe('ChatPanel', () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [], currentState: null, status: 'idle' })
  })

  it('纯文字结果与 report 渲染在对话中', () => {
    render(
      <ChatPanel
        report="# 分析报告"
        textSteps={[{ tool: 'go_kegg', status: 'completed', result: { kegg: [] } }]}
      />,
    )
    expect(screen.getByRole('heading', { name: '分析报告' })).toBeInTheDocument()
    expect(screen.getByText(/kegg/)).toBeInTheDocument()
  })
})
