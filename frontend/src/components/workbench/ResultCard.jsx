import { useState } from 'react'
import ThemeButton from '../common/ThemeButton'

function ResultCard({ res, added, onAddToSession, themeStyle }) {
  const [imageFailed, setImageFailed] = useState(false)

  const resultUrl = res.rawUrl || res.content || res.url || ''
  const filename = res.filename || '未命名文件'

  if (res.type === 'plot') {
    // 没有图片地址，直接不显示图表卡片
    if (!resultUrl) {
      return null
    }

    // 图片加载失败后，整张图表卡片不显示
    if (imageFailed) {
      return null
    }

    return (
      <div className="result-card">
        <h3>{res.title || '📊 分析图表'}</h3>

        <div className="result-content">
          <img
            src={resultUrl}
            alt={filename || 'Analysis Plot'}
            style={{
              display: 'block',
              maxWidth: '100%',
              borderRadius: '12px',
              border: `1px solid ${themeStyle.primaryBorder}`,
              background: '#ffffff'
            }}
            onError={() => {
              setImageFailed(true)
            }}
          />

          <div
            style={{
              marginTop: '10px',
              display: 'flex',
              gap: '10px',
              flexWrap: 'wrap'
            }}
          >
            <a
              href={resultUrl}
              target="_blank"
              rel="noreferrer"
              download={filename || true}
              style={{
                textDecoration: 'none',
                display: 'inline-flex',
                alignItems: 'center'
              }}
            >
              <ThemeButton themeStyle={themeStyle} variant="secondary">
                下载图片
              </ThemeButton>
            </a>

            <ThemeButton
              themeStyle={themeStyle}
              variant={added ? 'secondary' : 'primary'}
              disabled={added}
              onClick={() => onAddToSession(res)}
            >
              {added ? '已加入会话' : '加入到会话'}
            </ThemeButton>
          </div>
        </div>
      </div>
    )
  }

  if (res.type === 'file') {
    if (!resultUrl) {
      return null
    }

    return (
      <div className="result-card">
        <h3>{res.title || '📄 分析文件'}</h3>

        <div className="result-content">
          <p style={{ marginBottom: '10px', wordBreak: 'break-all' }}>
            文件名：{filename}
          </p>

          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <a
              href={resultUrl}
              target="_blank"
              rel="noreferrer"
              download={filename || true}
              style={{
                textDecoration: 'none',
                display: 'inline-flex',
                alignItems: 'center'
              }}
            >
              <ThemeButton themeStyle={themeStyle} variant="secondary">
                下载文件
              </ThemeButton>
            </a>

            <ThemeButton
              themeStyle={themeStyle}
              variant={added ? 'secondary' : 'primary'}
              disabled={added}
              onClick={() => onAddToSession(res)}
            >
              {added ? '已加入会话' : '加入到会话'}
            </ThemeButton>
          </div>
        </div>
      </div>
    )
  }

  if (!res.content) {
    return null
  }

  return (
    <div className="result-card">
      <h3>{res.title || '结果'}</h3>
      <div className="result-content">
        <p>{res.content}</p>
      </div>
    </div>
  )
}

export default ResultCard