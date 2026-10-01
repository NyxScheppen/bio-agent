import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  Bot,
  CheckCircle2,
  ChevronRight,
  Database,
  Download,
  File,
  FileSpreadsheet,
  FlaskConical,
  History,
  Image as ImageIcon,
  LoaderCircle,
  Menu,
  MessageSquarePlus,
  Paperclip,
  Plus,
  Send,
  Server,
  Trash2,
  Upload,
  X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  deleteSession,
  deleteUpload,
  getSession,
  healthCheck,
  listSessions,
  listUploads,
  normalizeArtifact,
  sendChat,
  uploadFiles,
} from './api'
import type { Artifact, Message, SessionSummary } from './types'

const THEMES = [
  { id: 'forest', label: '森林', color: '#087f5b' },
  { id: 'ocean', label: '海洋', color: '#176b87' },
  { id: 'rose', label: '樱花', color: '#b4235a' },
  { id: 'sunlight', label: '暖阳', color: '#a85a00' },
] as const

type ThemeId = (typeof THEMES)[number]['id']

function newSessionId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `session-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function messageId(): string {
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function formatBytes(value?: number): string {
  if (value == null) return ''
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / (1024 * 1024)).toFixed(1)} MB`
}

function isImage(file: Artifact): boolean {
  return file.type === 'image' || /\.(png|jpe?g|gif|webp|svg)$/i.test(file.name)
}

function fileIcon(file: Artifact) {
  if (isImage(file)) return <ImageIcon aria-hidden="true" />
  if (/\.(csv|tsv|xlsx?)$/i.test(file.name) || file.type === 'table') {
    return <FileSpreadsheet aria-hidden="true" />
  }
  return <File aria-hidden="true" />
}

function uniqueArtifacts(files: Artifact[]): Artifact[] {
  const seen = new Set<string>()
  return files.filter((file) => {
    if (seen.has(file.relativePath)) return false
    seen.add(file.relativePath)
    return true
  })
}

function App() {
  const [sessionId, setSessionId] = useState(newSessionId)
  const [sessions, setSessions] = useState<SessionSummary[]>([])
  const [messages, setMessages] = useState<Message[]>([])
  const [uploads, setUploads] = useState<Artifact[]>([])
  const [generated, setGenerated] = useState<Artifact[]>([])
  const [draft, setDraft] = useState('')
  const [theme, setTheme] = useState<ThemeId>('forest')
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [online, setOnline] = useState<boolean | null>(null)
  const [error, setError] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)
  const transcriptEnd = useRef<HTMLDivElement>(null)

  const allArtifacts = useMemo(
    () => uniqueArtifacts([...generated, ...uploads]),
    [generated, uploads],
  )

  async function refreshSessions() {
    try {
      setSessions(await listSessions())
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法加载会话历史')
    }
  }

  useEffect(() => {
    void listSessions().then(setSessions).catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : '无法加载会话历史')
    })
    void healthCheck().then(setOnline)
  }, [])

  useEffect(() => {
    transcriptEnd.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  function startNewSession() {
    setSessionId(newSessionId())
    setMessages([])
    setUploads([])
    setGenerated([])
    setDraft('')
    setError('')
    setSidebarOpen(false)
  }

  async function openSession(id: string) {
    if (busy || id === sessionId) {
      setSidebarOpen(false)
      return
    }
    setError('')
    try {
      const [history, currentUploads] = await Promise.all([getSession(id), listUploads(id)])
      const historyFiles = history.files
        .map((item) => normalizeArtifact(item as unknown as Record<string, unknown>))
        .filter((item): item is Artifact => item !== null)
      setSessionId(id)
      setMessages(
        history.messages
          .filter((item) => item.role === 'user' || item.role === 'assistant' || item.role === 'ai')
          .map((item) => ({
            id: messageId(),
            role: item.role === 'user' ? 'user' : 'assistant',
            content: item.content,
          })),
      )
      setUploads(currentUploads)
      setGenerated(historyFiles.filter((item) => item.sourceType !== 'upload'))
      setSidebarOpen(false)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '无法打开该会话')
    }
  }

  async function removeSession(id: string) {
    if (!window.confirm('删除此会话及其不再被引用的文件？')) return
    setError('')
    try {
      await deleteSession(id)
      if (id === sessionId) startNewSession()
      await refreshSessions()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '会话删除失败')
    }
  }

  async function handleUpload(selected: FileList | null) {
    const files = Array.from(selected ?? [])
    if (!files.length) return
    setUploading(true)
    setError('')
    try {
      const saved = await uploadFiles(sessionId, files)
      setUploads((current) => uniqueArtifacts([...current, ...saved]))
      await refreshSessions()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '文件上传失败')
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function removeUpload(file: Artifact) {
    setError('')
    try {
      await deleteUpload(sessionId, file.name)
      setUploads((current) => current.filter((item) => item.relativePath !== file.relativePath))
      await refreshSessions()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '文件删除失败')
    }
  }

  async function submit() {
    const content = draft.trim()
    if (!content || busy) return
    const userMessage: Message = { id: messageId(), role: 'user', content }
    const requestMessages = [...messages, userMessage]
    setMessages((current) => [...current, userMessage])
    setDraft('')
    setBusy(true)
    setError('')
    try {
      const result = await sendChat(sessionId, requestMessages, uploads)
      const resultFiles = (result.files ?? [])
        .map(normalizeArtifact)
        .filter((item): item is Artifact => item !== null)
      setMessages((current) => [
        ...current,
        { id: messageId(), role: 'assistant', content: result.reply, files: resultFiles },
      ])
      setGenerated((current) => uniqueArtifacts([...resultFiles, ...current]))
      await refreshSessions()
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : '分析请求失败'
      setError(message)
      setMessages((current) => [
        ...current,
        { id: messageId(), role: 'assistant', content: `请求未完成：${message}` },
      ])
    } finally {
      setBusy(false)
    }
  }

  function onComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void submit()
    }
  }

  return (
    <div className="app-shell" data-theme={theme}>
      <header className="topbar">
        <button className="icon-button mobile-menu" onClick={() => setSidebarOpen(true)} aria-label="打开会话列表">
          <Menu aria-hidden="true" />
        </button>
        <div className="brand-mark"><FlaskConical aria-hidden="true" /></div>
        <div className="brand-copy">
          <strong>BioAI Agent</strong>
          <span>Reproducible bioinformatics workspace</span>
        </div>
        <div className={`server-state ${online === true ? 'online' : online === false ? 'offline' : ''}`}>
          <span className="status-dot" />
          <Server aria-hidden="true" />
          {online === null ? '检测中' : online ? '服务正常' : '服务离线'}
        </div>
      </header>

      <div className="workspace">
        <aside className={`session-sidebar ${sidebarOpen ? 'open' : ''}`}>
          <div className="sidebar-heading">
            <span><History aria-hidden="true" />会话</span>
            <button className="icon-button sidebar-close" onClick={() => setSidebarOpen(false)} aria-label="关闭会话列表">
              <X aria-hidden="true" />
            </button>
          </div>
          <button className="new-session" onClick={startNewSession}>
            <MessageSquarePlus aria-hidden="true" />新建会话
          </button>
          <div className="session-list">
            {sessions.length === 0 && <p className="empty-small">还没有保存的会话</p>}
            {sessions.map((session) => (
              <div className={`session-row ${session.session_id === sessionId ? 'active' : ''}`} key={session.session_id}>
                <button className="session-main" onClick={() => void openSession(session.session_id)}>
                  <strong>{session.title || '新会话'}</strong>
                  <span>{session.message_count} 条消息 · {session.file_count} 个文件</span>
                </button>
                <button className="session-delete" onClick={() => void removeSession(session.session_id)} aria-label={`删除 ${session.title}`}>
                  <Trash2 aria-hidden="true" />
                </button>
              </div>
            ))}
          </div>
          <div className="sidebar-foot">
            <Database aria-hidden="true" />
            <span>会话与文件保存在本机</span>
          </div>
        </aside>
        {sidebarOpen && <button className="sidebar-scrim" onClick={() => setSidebarOpen(false)} aria-label="关闭会话列表" />}

        <main className="chat-workspace">
          <div className="chat-heading">
            <div>
              <span className="eyebrow">当前工作区</span>
              <h1>{sessions.find((item) => item.session_id === sessionId)?.title || '新的分析会话'}</h1>
            </div>
            <div className="theme-control" aria-label="页面配色">
              {THEMES.map((item) => (
                <button
                  className={theme === item.id ? 'active' : ''}
                  key={item.id}
                  onClick={() => setTheme(item.id)}
                  aria-pressed={theme === item.id}
                  aria-label={`${item.label}配色`}
                  title={`${item.label}配色`}
                >
                  <span className="theme-swatch" style={{ backgroundColor: item.color }} />
                  <span>{item.label}</span>
                </button>
              ))}
            </div>
          </div>

          {error && (
            <div className="error-banner" role="alert">
              <Activity aria-hidden="true" /><span>{error}</span>
              <button className="icon-button" onClick={() => setError('')} aria-label="关闭错误提示"><X /></button>
            </div>
          )}

          <section className="transcript" aria-live="polite">
            {messages.length === 0 && (
              <div className="empty-state">
                <div className="empty-symbol"><Bot aria-hidden="true" /></div>
                <h2>从一个生物学问题开始</h2>
                <p>上传数据并描述目标。系统会选择合适的 Skill、规划步骤、执行工具并返回可下载的结果。</p>
                <div className="starter-grid">
                  <button onClick={() => setDraft('检查上传的表达矩阵，并给出适合的差异分析方案')}>表达矩阵质检<ChevronRight /></button>
                  <button onClick={() => setDraft('根据上传数据执行生存分析，并解释结果边界')}>生存分析<ChevronRight /></button>
                  <button onClick={() => setDraft('对差异基因执行富集分析，明确记录外部服务状态')}>富集分析<ChevronRight /></button>
                </div>
              </div>
            )}
            {messages.map((message) => (
              <article className={`message ${message.role}`} key={message.id}>
                <div className="message-avatar">
                  {message.role === 'assistant' ? <Bot aria-hidden="true" /> : <span>你</span>}
                </div>
                <div className="message-body">
                  <div className="message-meta">{message.role === 'assistant' ? 'BioAI Agent' : '你'}</div>
                  <div className="markdown">
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
                      a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a>,
                    }}>{message.content}</ReactMarkdown>
                  </div>
                  {message.files && message.files.length > 0 && (
                    <div className="message-files">
                      {message.files.map((file) => (
                        <a href={file.url} target="_blank" rel="noreferrer" key={file.relativePath}>
                          {fileIcon(file)}<span>{file.name}</span><Download aria-hidden="true" />
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              </article>
            ))}
            {busy && (
              <article className="message assistant pending">
                <div className="message-avatar"><Bot aria-hidden="true" /></div>
                <div className="message-body">
                  <div className="message-meta">BioAI Agent</div>
                  <div className="thinking"><LoaderCircle className="spin" aria-hidden="true" />正在规划与执行分析</div>
                </div>
              </article>
            )}
            <div ref={transcriptEnd} />
          </section>

          <div className="composer-wrap">
            {uploads.length > 0 && (
              <div className="attachment-strip">
                {uploads.map((file) => (
                  <span key={file.relativePath}><Paperclip />{file.name}</span>
                ))}
              </div>
            )}
            <div className="composer">
              <button className="icon-button attach-button" onClick={() => fileInput.current?.click()} disabled={uploading || busy} aria-label="上传文件">
                {uploading ? <LoaderCircle className="spin" /> : <Plus />}
              </button>
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onComposerKeyDown}
                placeholder="描述分析目标"
                rows={1}
                disabled={busy}
              />
              <button className="send-button" onClick={() => void submit()} disabled={busy || !draft.trim()} aria-label="发送消息">
                {busy ? <LoaderCircle className="spin" /> : <Send />}
              </button>
            </div>
            <p className="composer-note">结果取决于输入质量、依赖环境与外部数据库可用性，请复核关键结论。</p>
          </div>
        </main>

        <aside className="artifact-sidebar">
          <div className="artifact-heading">
            <div><span className="eyebrow">会话资产</span><h2>文件与结果</h2></div>
            <button className="icon-button" onClick={() => fileInput.current?.click()} disabled={uploading || busy} aria-label="上传文件"><Upload /></button>
          </div>
          <input ref={fileInput} className="visually-hidden" type="file" multiple onChange={(event) => void handleUpload(event.target.files)} />
          <button className="upload-zone" onClick={() => fileInput.current?.click()} disabled={uploading || busy}>
            {uploading ? <LoaderCircle className="spin" /> : <Upload />}
            <span><strong>{uploading ? '正在上传' : '添加数据文件'}</strong><small>支持多文件，单次限制由后端配置</small></span>
          </button>
          <div className="artifact-list">
            {allArtifacts.length === 0 && (
              <div className="artifact-empty"><File aria-hidden="true" /><p>上传的数据和分析生成物会出现在这里。</p></div>
            )}
            {allArtifacts.map((file) => (
              <div className="artifact-item" key={file.relativePath}>
                {isImage(file) && <a className="image-preview" href={file.url} target="_blank" rel="noreferrer"><img src={file.url} alt={file.name} /></a>}
                <div className="artifact-row">
                  <div className="file-kind">{fileIcon(file)}</div>
                  <a className="artifact-name" href={file.url} target="_blank" rel="noreferrer">
                    <strong>{file.name}</strong><span>{file.sourceType === 'generated' || file.relativePath.startsWith('generated/') ? '分析结果' : '已上传'} {formatBytes(file.sizeBytes)}</span>
                  </a>
                  {file.relativePath.startsWith('uploads/') ? (
                    <button className="icon-button remove-file" onClick={() => void removeUpload(file)} aria-label={`删除 ${file.name}`}><Trash2 /></button>
                  ) : (
                    <a className="icon-button" href={file.url} download aria-label={`下载 ${file.name}`}><Download /></a>
                  )}
                </div>
              </div>
            ))}
          </div>
          <div className="artifact-summary"><CheckCircle2 /><span>{uploads.length} 个输入 · {generated.length} 个结果</span></div>
        </aside>
      </div>
    </div>
  )
}

export default App
