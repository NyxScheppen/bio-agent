import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

function MessageList({
  messages,
  isLoading,
  loadingText,
  normalizeToAbsoluteFileUrl,
  messagesEndRef
}) {
  const safeNormalizeUrl = (url) => {
    if (!url) return ''
    try {
      return normalizeToAbsoluteFileUrl ? normalizeToAbsoluteFileUrl(url) : url
    } catch {
      return url
    }
  }

  return (
    <div className="chat-window">
      {(messages || []).map((msg, index) => (
        <div key={index} className={`message-wrapper ${msg.role}`}>
          <div className={`message-bubble ${msg.role}`}>
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  const finalHref = safeNormalizeUrl(href)

                  return (
                    <a
                      href={finalHref}
                      target="_blank"
                      rel="noreferrer"
                      download={finalHref.includes('/files/') ? true : undefined}
                    >
                      {children}
                    </a>
                  )
                },

                img: ({ src, alt }) => {
                  const finalSrc = safeNormalizeUrl(src)

                  if (!finalSrc) return null

                  return (
                    <div className="markdown-image-wrap">
                      <img
                        src={finalSrc}
                        alt={alt || 'result'}
                        className="markdown-image"
                        onError={(e) => {
                          const wrapper = e.currentTarget.closest('.markdown-image-wrap')
                          if (wrapper) {
                            wrapper.style.display = 'none'
                          } else {
                            e.currentTarget.style.display = 'none'
                          }
                        }}
                      />

                      <div className="markdown-image-actions">
                        <a href={finalSrc} target="_blank" rel="noreferrer" download>
                          下载/打开图片
                        </a>
                      </div>
                    </div>
                  )
                },

                table: ({ children }) => (
                  <div className="markdown-table-wrap">
                    <table>{children}</table>
                  </div>
                ),

                code: ({ inline, children }) => {
                  if (inline) {
                    return <code className="markdown-inline-code">{children}</code>
                  }

                  return (
                    <pre className="markdown-code-block">
                      <code>{children}</code>
                    </pre>
                  )
                }
              }}
            >
              {msg.content || ''}
            </ReactMarkdown>
          </div>
        </div>
      ))}

      {isLoading && (
        <div className="message-wrapper ai">
          <div className="message-bubble ai thinking-bubble">
            <div className="typing-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <span className="thinking-text">
              {loadingText}
              <span className="thinking-ellipsis">
                <span>.</span>
                <span>.</span>
                <span>.</span>
              </span>
            </span>
          </div>
        </div>
      )}

      <div ref={messagesEndRef} />
    </div>
  )
}

export default MessageList