import { getDangerButtonStyle, getSourceBadgeStyle } from '../../utils/themeHelpers'

function AttachedFileCard({ file, themeStyle, sourceType, onDelete }) {
  const isGenerated = sourceType === 'generated'

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        gap: '10px',
        padding: '10px 12px',
        borderRadius: '10px',
        background: themeStyle.lightPanel
      }}
    >
      <div style={{ minWidth: 0 }}>
        <div
          style={{
            fontWeight: 600,
            wordBreak: 'break-all',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            flexWrap: 'wrap'
          }}
        >
          <span>{file.filename}</span>
          <span style={getSourceBadgeStyle(themeStyle, isGenerated)}>
            {isGenerated ? '生成' : '上传'}
          </span>
        </div>
        <div
          style={{
            fontSize: '12px',
            opacity: 0.7,
            marginTop: '4px',
            wordBreak: 'break-all'
          }}
        >
          {file.type || 'other'}
          {typeof file.size_bytes === 'number'
            ? ` · ${Math.max(1, Math.round(file.size_bytes / 1024))} KB`
            : ''}
          {(file.relative_path || file.relativePath) &&
            ` · ${file.relative_path || file.relativePath}`}
        </div>
      </div>

      <button
        onClick={() => onDelete(file.filename)}
        title={`删除 ${file.filename}`}
        aria-label={`删除 ${file.filename}`}
        style={getDangerButtonStyle(themeStyle)}
      >
        ×
      </button>
    </div>
  )
}

export default AttachedFileCard