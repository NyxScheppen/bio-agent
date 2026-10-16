import { useRef } from 'react'
import ThemeButton from '../common/ThemeButton'

function ChatInput({
  userInput,
  setUserInput,
  sendMessage,
  isLoading,
  fileInputRef,
  handleFileUpload,
  inputPlaceholder,
  uploadIcon,
  themeStyle
}) {
  const textareaRef = useRef(null)

  const resizeTextarea = () => {
    const textarea = textareaRef.current
    if (!textarea) return

    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`
  }

  const resetTextareaHeight = () => {
    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = '44px'
      }
    })
  }

  const handleInputChange = (e) => {
    setUserInput(e.target.value)

    requestAnimationFrame(() => {
      resizeTextarea()
    })
  }

  const handleKeyDown = (e) => {
    // Enter 默认换行，不拦截
    // Ctrl + Enter / Cmd + Enter 才发送
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()

      if (isLoading) return
      if (!userInput.trim()) return

      sendMessage()
      resetTextareaHeight()
    }
  }

  const handleSendClick = () => {
    if (isLoading) return
    if (!userInput.trim()) return

    sendMessage()
    resetTextareaHeight()
  }

  return (
    <div className="input-area">
      <div className="input-container">
        <input
          type="file"
          ref={fileInputRef}
          style={{ display: 'none' }}
          multiple
          onChange={handleFileUpload}
        />

        <ThemeButton
          themeStyle={themeStyle}
          onClick={() => fileInputRef.current?.click()}
          disabled={isLoading}
          title="上传文件"
          aria-label="上传文件"
          style={{
            minWidth: '44px',
            height: '44px',
            borderRadius: '12px',
            boxShadow: `0 8px 18px ${themeStyle.primarySoft}`
          }}
        >
          {uploadIcon}
        </ThemeButton>

        <textarea
          ref={textareaRef}
          value={userInput}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder={inputPlaceholder || '输入你的分析需求，Enter 换行，Ctrl/Cmd + Enter 发送'}
          rows={1}
          disabled={isLoading}
          style={{
            flex: 1,
            minHeight: '44px',
            maxHeight: '160px',
            resize: 'none',
            overflowY: 'auto',
            border: `1px solid ${themeStyle.primaryBorder}`,
            borderRadius: '12px',
            padding: '11px 14px',
            lineHeight: '20px',
            fontSize: '15px',
            outline: 'none',
            background: isLoading ? '#f3f4f6' : '#ffffff',
            color: '#111827',
            boxSizing: 'border-box',
            fontFamily: 'inherit',
            whiteSpace: 'pre-wrap'
          }}
        />

        <ThemeButton
          themeStyle={themeStyle}
          onClick={handleSendClick}
          disabled={isLoading || !userInput.trim()}
          style={{
            minWidth: '74px',
            height: '44px',
            borderRadius: '12px',
            boxShadow: `0 8px 18px ${themeStyle.primarySoft}`
          }}
        >
          发送
        </ThemeButton>
      </div>
    </div>
  )
}

export default ChatInput