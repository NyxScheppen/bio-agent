function SessionCard({ session, active, themeStyle, onSelect, onDelete }) {
  return (
    <div
      onClick={() => onSelect(session.id)}
      style={{
        marginBottom: '10px',
        padding: '12px',
        borderRadius: '14px',
        cursor: 'pointer',
        background: active ? 'rgba(255,255,255,0.96)' : 'rgba(255,255,255,0.16)',
        border: active
          ? '1px solid rgba(255,255,255,0.65)'
          : '1px solid rgba(255,255,255,0.18)',
        boxShadow: active ? '0 10px 24px rgba(0,0,0,0.12)' : 'none',
        backdropFilter: 'blur(8px)',
        transition: 'all 0.2s ease'
      }}
    >
      <div
        style={{
          fontSize: '14px',
          fontWeight: 700,
          lineHeight: 1.4,
          wordBreak: 'break-word',
          marginBottom: '8px',
          color: active ? '#111827' : '#ffffff'
        }}
      >
        {session.title || '新会话'}
      </div>

      <div
        style={{
          fontSize: '12px',
          color: active ? '#4b5563' : 'rgba(255,255,255,0.82)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}
      >
        <span>{session.messages?.length || 0} 条消息</span>
        <button
          onClick={(e) => onDelete(session.id, e)}
          style={{
            background: 'transparent',
            color: active ? themeStyle.primary : '#ffffff',
            border: 'none',
            cursor: 'pointer',
            fontWeight: 700
          }}
        >
          删除
        </button>
      </div>
    </div>
  )
}

export default SessionCard