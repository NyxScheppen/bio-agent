import ThemeButton from '../common/ThemeButton'
import SessionCard from '../session/SessionCard'

function Sidebar({
  sidebarWidth,
  sessions,
  currentSessionId,
  themeStyle,
  onNewSession,
  onSelectSession,
  onDeleteSession
}) {
  return (
    <div
      className="sidebar-section"
      style={{
        width: sidebarWidth,
        background: `linear-gradient(180deg, ${themeStyle.sidebarGradientFrom} 0%, ${themeStyle.sidebarGradientTo} 100%)`,
        color: themeStyle.sidebarText
      }}
    >
      <div
        style={{
          padding: '16px',
          borderBottom: '1px solid rgba(255,255,255,0.18)'
        }}
      >
        <ThemeButton
          themeStyle={themeStyle}
          variant="secondary"
          onClick={onNewSession}
          style={{
            width: '100%',
            padding: '12px 14px',
            fontWeight: 700,
            background: 'rgba(255,255,255,0.92)',
            color: themeStyle.primary,
            border: '1px solid rgba(255,255,255,0.55)',
            boxShadow: '0 8px 18px rgba(0,0,0,0.08)'
          }}
        >
          ＋ 新会话
        </ThemeButton>
      </div>

      <div
        style={{
          padding: '12px',
          fontSize: '12px',
          color: themeStyle.sidebarMuted,
          letterSpacing: '0.08em',
          fontWeight: 700
        }}
      >
        历史会话
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 10px 10px' }}>
        {sessions.map((session) => (
          <SessionCard
            key={session.id}
            session={session}
            active={session.id === currentSessionId}
            themeStyle={themeStyle}
            onSelect={onSelectSession}
            onDelete={onDeleteSession}
          />
        ))}
      </div>
    </div>
  )
}

export default Sidebar