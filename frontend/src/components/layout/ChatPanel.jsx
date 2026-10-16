import { AGENT_AVATARS, AGENT_OPTIONS } from '../../constants/agentConfig'
import MessageList from '../chat/MessageList'
import ChatInput from '../chat/ChatInput'

function ChatPanel({
  leftWidth,
  currentSession,
  currentTheme,
  currentAgentLabel,
  themeStyle,
  isLoading,
  loadingText,
  userInput,
  setUserInput,
  sendMessage,
  fileInputRef,
  handleFileUpload,
  inputPlaceholder,
  uploadIcon,
  handleAgentSwitch,
  normalizeToAbsoluteFileUrl,
  messagesEndRef
}) {
  return (
    <div className="chat-section" style={{ width: leftWidth }}>
      <div className="chat-card">
        <div className="chat-header">
          <div
            style={{
              fontSize: '24px',
              background: `linear-gradient(135deg, ${themeStyle.headerBg}, #ffffff)`,
              padding: '10px',
              borderRadius: '14px',
              border: `1px solid ${themeStyle.primaryBorder}`,
              boxShadow: `0 8px 20px ${themeStyle.primarySoft}`
            }}
          >
            {AGENT_AVATARS[currentTheme]}
          </div>

          <div className="header-info">
            <h2>{currentSession?.title || 'BioAgent Hub'}</h2>
            <p>● ONLINE</p>
            <div
              style={{
                marginTop: '6px',
                fontSize: '14px',
                fontWeight: 700,
                color: themeStyle.primary
              }}
            >
              当前模式：{currentAgentLabel}
            </div>
          </div>
        </div>

        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            padding: '10px 20px 14px 20px',
            borderBottom: `1px solid ${themeStyle.primaryBorder}`,
            background: `linear-gradient(180deg, ${themeStyle.lightPanel} 0%, #ffffff 100%)`
          }}
        >
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {AGENT_OPTIONS.map((agent) => {
              const active = currentTheme === agent.key

              return (
                <button
                  key={agent.key}
                  onClick={() => handleAgentSwitch(agent)}
                  disabled={isLoading}
                  style={{
                    padding: '8px 14px',
                    borderRadius: '999px',
                    border: active
                      ? `2px solid ${themeStyle.primary}`
                      : `1px solid ${themeStyle.primaryBorder}`,
                    background: active ? themeStyle.primarySoft : '#ffffff',
                    color: active ? themeStyle.primary : '#111827',
                    fontWeight: active ? 700 : 500,
                    cursor: isLoading ? 'not-allowed' : 'pointer',
                    opacity: isLoading ? 0.6 : 1,
                    transition: 'all 0.2s ease',
                    boxShadow: active ? `0 8px 18px ${themeStyle.primarySoft}` : 'none'
                  }}
                >
                  {agent.label}
                </button>
              )
            })}
          </div>
        </div>

        <MessageList
          messages={currentSession?.messages || []}
          isLoading={isLoading}
          loadingText={loadingText}
          normalizeToAbsoluteFileUrl={normalizeToAbsoluteFileUrl}
          messagesEndRef={messagesEndRef}
        />

        <ChatInput
          userInput={userInput}
          setUserInput={setUserInput}
          sendMessage={sendMessage}
          isLoading={isLoading}
          fileInputRef={fileInputRef}
          handleFileUpload={handleFileUpload}
          inputPlaceholder={inputPlaceholder}
          uploadIcon={uploadIcon}
          themeStyle={themeStyle}
        />
      </div>
    </div>
  )
}

export default ChatPanel