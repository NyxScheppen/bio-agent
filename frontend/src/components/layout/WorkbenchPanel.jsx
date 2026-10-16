import AttachedFileCard from '../workbench/AttachedFileCard'
import ResultCard from '../workbench/ResultCard'

function WorkbenchPanel({
  currentSession,
  themeStyle,
  handleDeleteUploadedFile,
  isFileAlreadyAttached,
  getRelativePathFromUrl,
  addResultToCurrentSession
}) {
  return (
    <div className="workbench-section">
      <div className="workbench-header">
        <span
          className="lab-tag"
          style={{
            background: `linear-gradient(135deg, ${themeStyle.labBg}, ${themeStyle.primaryDark})`,
            color: themeStyle.labText,
            boxShadow: `0 8px 20px ${themeStyle.primarySoft}`,
            border: `1px solid ${themeStyle.primaryBorder}`
          }}
        >
          LAB
        </span>
        <h3>Analysis Workbench</h3>
      </div>

      <div className="result-card">
        <h3>📁 当前会话文件</h3>
        <div className="result-content">
          {(currentSession?.attachedFiles || []).length === 0 ? (
            <p>当前会话还没有上传文件。</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {currentSession.attachedFiles.map((file) => {
                const sourceType = file.source_type || 'upload'
                return (
                  <AttachedFileCard
                    key={`${file.relative_path || file.url || file.filename}`}
                    file={file}
                    themeStyle={themeStyle}
                    sourceType={sourceType}
                    onDelete={handleDeleteUploadedFile}
                  />
                )
              })}
            </div>
          )}
        </div>
      </div>

      {(currentSession?.results || []).map((res, index) => {
        const added = isFileAlreadyAttached(currentSession, {
          filename: res.filename,
          relative_path: res.relativePath || getRelativePathFromUrl(res.rawUrl || res.content),
          url: res.rawUrl || res.content
        })

        return (
          <ResultCard
            key={res.id || index}
            res={res}
            added={added}
            onAddToSession={addResultToCurrentSession}
            themeStyle={themeStyle}
          />
        )
      })}
    </div>
  )
}

export default WorkbenchPanel