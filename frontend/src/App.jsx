import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

import Sidebar from './components/layout/Sidebar'
import ChatPanel from './components/layout/ChatPanel'
import WorkbenchPanel from './components/layout/WorkbenchPanel'

import {
  API_BASE,
  AGENT_OPTIONS,
  AGENT_WELCOME_MESSAGES,
  AGENT_STATUS_MESSAGES,
  AGENT_LOADING_MESSAGES,
  AGENT_UPLOAD_ICONS,
  AGENT_INPUT_PLACEHOLDERS,
  THEME_STYLE_MAP
} from './constants/agentConfig'

import {
  normalizeToAbsoluteFileUrl,
  getRelativePathFromUrl,
  buildResultFromFile,
  mergeSessionResults,
  isFileAlreadyAttached,
  getCanonicalResultKey,
  isImagePath
} from './utils/fileHelpers'

const createSession = (agentMode = 'bird') => {
  const id =
    window.crypto && window.crypto.randomUUID
      ? window.crypto.randomUUID()
      : `session_${Date.now()}_${Math.floor(Math.random() * 10000)}`

  return {
    id,
    title: '新会话',
    attachedFiles: [],
    agentMode,
    messages: [
      {
        role: 'ai',
        content: AGENT_WELCOME_MESSAGES[agentMode] || AGENT_WELCOME_MESSAGES.bird
      }
    ],
    results: [
      {
        id: `status_${Date.now()}`,
        type: 'text',
        title: '🧬 实验室状态',
        content: AGENT_STATUS_MESSAGES[agentMode] || AGENT_STATUS_MESSAGES.bird
      }
    ]
  }
}

function App() {
  const [sessions, setSessions] = useState(() => {
    const saved = localStorage.getItem('bio_agent_sessions')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length > 0) {
          return parsed.map((session) => {
            const rawMode = session.agentMode || session.animalMode || 'bird'
            const mappedMode =
              rawMode === 'red'
                ? 'bird'
                : rawMode === 'green'
                  ? 'fox'
                  : rawMode === 'blue'
                    ? 'lion'
                    : rawMode === 'purple'
                      ? 'snake'
                      : rawMode === 'default'
                        ? 'bird'
                        : rawMode

            return {
              ...session,
              attachedFiles: Array.isArray(session.attachedFiles)
                ? session.attachedFiles
                : session.attachedFile
                  ? [{ filename: session.attachedFile }]
                  : [],
              agentMode: mappedMode
            }
          })
        }
      } catch (e) {
        console.error('读取历史会话失败:', e)
      }
    }
    return [createSession()]
  })

  const [currentSessionId, setCurrentSessionId] = useState(() => {
    return localStorage.getItem('bio_agent_current_session_id') || null
  })

  const [userInput, setUserInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  const [sidebarWidth, setSidebarWidth] = useState(() => {
    const saved = localStorage.getItem('bio_agent_sidebar_width')
    return saved ? Number(saved) : 260
  })

  const [leftWidth, setLeftWidth] = useState(() => {
    const saved = localStorage.getItem('bio_agent_chat_width')
    return saved ? Number(saved) : window.innerWidth * 0.5
  })

  const resizeMode = useRef(null)
  const fileInputRef = useRef(null)
  const messagesEndRef = useRef(null)

  const currentSession = useMemo(
    () => sessions.find((s) => s.id === currentSessionId) || sessions[0] || null,
    [sessions, currentSessionId]
  )

  const currentTheme = currentSession?.agentMode || 'bird'
  const themeStyle = THEME_STYLE_MAP[currentTheme] || THEME_STYLE_MAP.bird
  const currentAgentLabel =
    AGENT_OPTIONS.find((a) => a.key === currentTheme)?.label || '🐦'
  const loadingText = AGENT_LOADING_MESSAGES[currentTheme] || AGENT_LOADING_MESSAGES.bird
  const uploadIcon = AGENT_UPLOAD_ICONS[currentTheme] || '📁'
  const inputPlaceholder =
    AGENT_INPUT_PLACEHOLDERS[currentTheme] || AGENT_INPUT_PLACEHOLDERS.bird

  useEffect(() => {
    if (!currentSessionId && sessions.length > 0) {
      setCurrentSessionId(sessions[0].id)
    }
  }, [currentSessionId, sessions])

  useEffect(() => {
    localStorage.setItem('bio_agent_sessions', JSON.stringify(sessions))
  }, [sessions])

  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem('bio_agent_current_session_id', currentSessionId)
    }
  }, [currentSessionId])

  useEffect(() => {
    localStorage.setItem('bio_agent_sidebar_width', String(sidebarWidth))
  }, [sidebarWidth])

  useEffect(() => {
    localStorage.setItem('bio_agent_chat_width', String(leftWidth))
  }, [leftWidth])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [sessions, currentSessionId, isLoading])

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!resizeMode.current) return

      const totalWidth = window.innerWidth
      const rightMinWidth = 320
      const chatMinWidth = 360
      const sidebarMinWidth = 220
      const sidebarMaxWidth = 420

      if (resizeMode.current === 'sidebar') {
        const nextSidebarWidth = e.clientX
        const maxAllowed = totalWidth - rightMinWidth - chatMinWidth - 12
        if (
          nextSidebarWidth >= sidebarMinWidth &&
          nextSidebarWidth <= Math.min(sidebarMaxWidth, maxAllowed)
        ) {
          setSidebarWidth(nextSidebarWidth)
        }
      }

      if (resizeMode.current === 'chat') {
        const nextChatWidth = e.clientX - sidebarWidth - 6
        const maxAllowed = totalWidth - sidebarWidth - rightMinWidth - 12
        if (nextChatWidth >= chatMinWidth && nextChatWidth <= maxAllowed) {
          setLeftWidth(nextChatWidth)
        }
      }
    }

    const stopResizing = () => {
      resizeMode.current = null
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', stopResizing)
      document.body.style.userSelect = 'auto'
      document.body.style.cursor = 'default'
    }

    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', stopResizing)

    return () => {
      document.removeEventListener('mousemove', handleMouseMove)
      document.removeEventListener('mouseup', stopResizing)
    }
  }, [sidebarWidth])

  useEffect(() => {
    if (currentSessionId) {
      fetchUploadedFiles(currentSessionId)
    }
  }, [currentSessionId])

  const startResizeSidebar = () => {
    resizeMode.current = 'sidebar'
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
  }

  const startResizeChat = () => {
    resizeMode.current = 'chat'
    document.body.style.userSelect = 'none'
    document.body.style.cursor = 'col-resize'
  }

  const updateSession = (sessionId, updater) => {
    setSessions((prev) =>
      prev.map((session) =>
        session.id === sessionId
          ? typeof updater === 'function'
            ? updater(session)
            : { ...session, ...updater }
          : session
      )
    )
  }

  const addResultToCurrentSession = (res) => {
    if (!currentSession) return
    if (!(res.type === 'plot' || res.type === 'file')) return

    const relativePath =
      res.relativePath || getRelativePathFromUrl(res.rawUrl || res.content, API_BASE)

    const fileItem = {
      filename: res.filename || relativePath.split('/').pop() || 'result_file',
      relative_path: relativePath,
      url: `/files/${relativePath}`,
      type: res.fileType || (res.type === 'plot' ? 'image' : 'other'),
      source_type: 'generated'
    }

    updateSession(currentSession.id, (session) => {
      if (isFileAlreadyAttached(session, fileItem)) {
        return session
      }

      return {
        ...session,
        attachedFiles: [...(session.attachedFiles || []), fileItem]
      }
    })
  }

  const normalizeBackendFiles = (backendFiles) => {
    if (!Array.isArray(backendFiles)) return []

    return backendFiles.map((file) => {
      const filename = file.filename || file.name || ''
      const relativePath = file.relative_path || file.relativePath || ''
      const url =
        file.url ||
        (relativePath
          ? `/files/${relativePath}`
          : filename
            ? `/files/${filename}`
            : '')

      const shouldBeImage =
        file.type === 'image' ||
        file.fileType === 'image' ||
        isImagePath(filename) ||
        isImagePath(relativePath) ||
        isImagePath(url)

      return {
        ...file,
        filename,
        relative_path: relativePath,
        url,
        type: shouldBeImage ? 'image' : file.type || 'other',
        source_type: file.source_type || file.sourceType || 'generated'
      }
    })
  }

  const updateWorkbench = (sessionId, aiReply, backendFiles = []) => {
    const markdownImgRegex = /!\[[^\]]*?\]\((.*?)\)/g
    const markdownLinkRegex = /\[([^\]]+)\]\((.*?)\)/g
    const plainUrlRegex =
      /(?:https?:\/\/[^)\s]+)?\/files\/[a-zA-Z0-9_./%-]+\.(png|jpg|jpeg|svg|gif|webp)(?:\?[^)\s]*)?|generated\/[a-zA-Z0-9_./%-]+\.(png|jpg|jpeg|svg|gif|webp)(?:\?[^)\s]*)?/gi

    const normalizedBackendFiles = normalizeBackendFiles(backendFiles)

    const backendByFilename = new Map()
    const backendByRelativePath = new Map()
    const resultMap = new Map()

    normalizedBackendFiles.forEach((file) => {
      const filename = file.filename || ''
      const relativePath = file.relative_path || ''
      if (filename) backendByFilename.set(filename, file)
      if (relativePath) backendByRelativePath.set(relativePath, file)
    })

    const pushUniqueResult = (item) => {
      if (!item) return
      const key = getCanonicalResultKey(item, API_BASE)
      if (!key) return

      const existing = resultMap.get(key)
      if (!existing) {
        resultMap.set(key, item)
        return
      }

      const existingHasRelative = !!(
        existing.relativePath ||
        getRelativePathFromUrl(existing.rawUrl || existing.content || '', API_BASE)
      )
      const currentHasRelative = !!(
        item.relativePath || getRelativePathFromUrl(item.rawUrl || item.content || '', API_BASE)
      )

      if (!existingHasRelative && currentHasRelative) {
        resultMap.set(key, item)
      }
    }

    const buildImageResult = (urlOrPath, title = '📊 分析图表') => {
      if (!urlOrPath) return null

      const rawInput = String(urlOrPath).trim()
      const normalizedUrl = normalizeToAbsoluteFileUrl(rawInput, API_BASE)
      const relativePath = getRelativePathFromUrl(normalizedUrl, API_BASE)
      const filename = normalizedUrl.split('?')[0].split('/').pop() || 'plot.png'

      const backendMatchByPath = backendByRelativePath.get(relativePath)
      const backendMatchByName = backendByFilename.get(filename)

      const backendMatch = backendMatchByPath || backendMatchByName

      if (backendMatch) {
        const fromBackend = buildResultFromFile(backendMatch, API_BASE)
        return {
          ...fromBackend,
          title
        }
      }

      if (!rawInput.includes('/') && !rawInput.startsWith('http')) {
        return null
      }

      return {
        id: `img_${relativePath || filename}_${Date.now()}_${Math.random()}`,
        type: 'plot',
        fileType: 'image',
        title,
        content: `${normalizedUrl}?t=${Date.now()}`,
        rawUrl: normalizedUrl,
        filename,
        relativePath,
        sourceType: 'generated'
      }
    }

    const buildFileResult = (text, urlOrPath) => {
      if (!urlOrPath) return null

      const rawInput = String(urlOrPath).trim()
      const normalizedUrl = normalizeToAbsoluteFileUrl(rawInput, API_BASE)
      const relativePath = getRelativePathFromUrl(normalizedUrl, API_BASE)
      const filename = text || normalizedUrl.split('?')[0].split('/').pop() || 'download'

      const backendMatchByPath = backendByRelativePath.get(relativePath)
      const backendMatchByName = backendByFilename.get(filename)

      const backendMatch = backendMatchByPath || backendMatchByName

      if (backendMatch) {
        return buildResultFromFile(backendMatch, API_BASE)
      }

      if (!rawInput.includes('/') && !rawInput.startsWith('http')) {
        return null
      }

      return {
        id: `file_${relativePath || filename}_${Date.now()}_${Math.random()}`,
        type: isImagePath(normalizedUrl) ? 'plot' : 'file',
        fileType: isImagePath(normalizedUrl) ? 'image' : 'other',
        title: isImagePath(normalizedUrl) ? `📊 ${filename}` : `📄 ${text || '结果文件'}`,
        content: isImagePath(normalizedUrl) ? `${normalizedUrl}?t=${Date.now()}` : normalizedUrl,
        rawUrl: normalizedUrl,
        filename,
        relativePath,
        sourceType: 'generated'
      }
    }

    let match
    while ((match = markdownImgRegex.exec(aiReply || '')) !== null) {
      const item = buildImageResult(match[1], '📊 分析图表')
      pushUniqueResult(item)
    }

    let urlMatch
    while ((urlMatch = plainUrlRegex.exec(aiReply || '')) !== null) {
      const item = buildImageResult(urlMatch[0], '📊 分析图表')
      pushUniqueResult(item)
    }

    let linkMatch
    while ((linkMatch = markdownLinkRegex.exec(aiReply || '')) !== null) {
      const text = linkMatch[1]
      const url = linkMatch[2]
      if (!url) continue

      const lower = String(url).toLowerCase()
      const isImage = /\.(png|jpg|jpeg|svg|gif|webp)(\?|$)/i.test(lower)

      if (isImage) {
        const item = buildImageResult(url, '📊 分析图表')
        pushUniqueResult(item)
      } else {
        const item = buildFileResult(text, url)
        pushUniqueResult(item)
      }
    }

    normalizedBackendFiles.forEach((file) => {
      pushUniqueResult(buildResultFromFile(file, API_BASE))
    })

    const newResults = Array.from(resultMap.values())

    if (newResults.length === 0) return

    updateSession(sessionId, (session) => ({
      ...session,
      results: mergeSessionResults(session, newResults, API_BASE)
    }))
  }

  const fetchUploadedFiles = async (sessionId) => {
    try {
      const response = await fetch(`${API_BASE}/api/uploads/${encodeURIComponent(sessionId)}`)
      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || '获取文件列表失败')
      }

      updateSession(sessionId, (session) => {
        const existing = session.attachedFiles || []
        const backendFiles = (data.files || []).map((file) => ({
          ...file,
          source_type: file.source_type || 'upload'
        }))

        const merged = [...existing]

        backendFiles.forEach((file) => {
          const exists = merged.some((f) => {
            const a = f.relative_path || f.relativePath || f.url || f.filename
            const b = file.relative_path || file.relativePath || file.url || file.filename
            return a === b
          })
          if (!exists) {
            merged.push(file)
          }
        })

        return {
          ...session,
          attachedFiles: merged
        }
      })
    } catch (error) {
      console.error('获取上传文件失败:', error)
    }
  }

  const sendCustomMessage = async (customText, options = {}) => {
    if (!currentSession) return
    if (!customText?.trim()) return
    if (isLoading) return

    const { clearInput = false } = options
    const newMessage = { role: 'user', content: customText }
    const updatedHistory = [...currentSession.messages, newMessage]

    updateSession(currentSession.id, {
      messages: updatedHistory
    })

    if (clearInput) {
      setUserInput('')
    }

    setIsLoading(true)

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: currentSession.id,
          messages: updatedHistory,
          attached_files: currentSession.attachedFiles || []
        })
      })

      const data = await response.json()

      if (!response.ok) {
        throw new Error(data.detail || '请求失败')
      }

      updateSession(currentSession.id, (session) => ({
        ...session,
        title: data.title || session.title,
        messages: [...session.messages, { role: 'ai', content: data.reply || '分析完成。' }]
      }))

      updateWorkbench(currentSession.id, data.reply || '', data.files || [])
    } catch (error) {
      updateSession(currentSession.id, (session) => ({
        ...session,
        messages: [
          ...session.messages,
          { role: 'ai', content: `❌ 请求失败：${error.message}` }
        ]
      }))
    } finally {
      setIsLoading(false)
    }
  }

  const handleNewSession = () => {
    const newSession = createSession('bird')
    setSessions((prev) => [newSession, ...prev])
    setCurrentSessionId(newSession.id)
    setUserInput('')
    setIsLoading(false)
  }

  const handleSelectSession = (sessionId) => {
    setCurrentSessionId(sessionId)
    setUserInput('')
  }

 const handleDeleteSession = async (sessionId, e) => {
  e.stopPropagation()

  const ok = window.confirm('确定删除这个会话吗？相关上传文件和生成文件也会一起删除。')
  if (!ok) return

  try {
    const response = await fetch(
      `${API_BASE}/api/chat/session/${encodeURIComponent(sessionId)}`,
      { method: 'DELETE' }
    )

    let data = {}
    try {
      data = await response.json()
    } catch {
      data = {}
    }

    if (!response.ok || data.status !== 'success') {
      throw new Error(data.message || '删除会话失败')
    }

    const filtered = sessions.filter((s) => s.id !== sessionId)

    if (filtered.length === 0) {
      const fresh = createSession('bird')
      setSessions([fresh])
      setCurrentSessionId(fresh.id)
      return
    }

    setSessions(filtered)
    if (currentSessionId === sessionId) {
      setCurrentSessionId(filtered[0].id)
    }
  } catch (error) {
    console.error('删除会话失败:', error)
    alert(error.message || '删除会话失败')
  }
}

  const handleAgentSwitch = (agent) => {
    if (!currentSession || isLoading) return

    updateSession(currentSession.id, (session) => ({
      ...session,
      agentMode: agent.key,
      results: (session.results || []).map((item, index) =>
        index === 0 && item.title === '🧬 实验室状态'
          ? {
              ...item,
              content: AGENT_STATUS_MESSAGES[agent.key] || item.content
            }
          : item
      )
    }))
  }

  const handleFileUpload = async (event) => {
    const files = Array.from(event.target.files || [])
    if (!files.length || !currentSession) return

    setIsLoading(true)

    const formData = new FormData()
    files.forEach((file) => {
      formData.append('files', file)
    })
    formData.append('session_id', currentSession.id)

    try {
      const response = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData
      })

      let data = {}
      try {
        data = await response.json()
      } catch {
        data = {}
      }

      if (!response.ok) {
        throw new Error(data.detail || `文件上传失败（${response.status}）`)
      }

      await fetchUploadedFiles(currentSession.id)

      updateSession(currentSession.id, (session) => ({
        ...session,
        title:
          session.title === '新会话' && data.files?.[0]?.filename
            ? data.files[0].filename
            : session.title
      }))
    } catch (error) {
      console.error('文件上传失败:', error)
      alert(error.message || '文件上传失败')
    } finally {
      setIsLoading(false)
      event.target.value = ''
    }
  }

  const handleDeleteUploadedFile = async (filename) => {
    if (!currentSession) return

    const target = (currentSession.attachedFiles || []).find((f) => f.filename === filename)
    const relativePath = target?.relative_path || target?.relativePath || ''
    const sourceType = target?.source_type || 'upload'
    const isUploadFile =
      sourceType === 'upload' || relativePath.startsWith(`uploads/${currentSession.id}/`)

    if (!isUploadFile) {
      updateSession(currentSession.id, (session) => ({
        ...session,
        attachedFiles: (session.attachedFiles || []).filter((f) => f.filename !== filename)
      }))
      return
    }

    try {
      const response = await fetch(
        `${API_BASE}/api/uploads/${encodeURIComponent(currentSession.id)}/${encodeURIComponent(filename)}`,
        { method: 'DELETE' }
      )

      let data = {}
      try {
        data = await response.json()
      } catch {
        data = {}
      }

      if (!response.ok) {
        throw new Error(data.detail || '删除失败')
      }

      updateSession(currentSession.id, (session) => ({
        ...session,
        attachedFiles: (session.attachedFiles || []).filter((f) => f.filename !== filename)
      }))
    } catch (error) {
      console.error('删除文件失败:', error)
      alert(error.message || '删除失败')
    }
  }

  const sendMessage = async () => {
    if (!currentSession) return
    if (!userInput.trim() && !(currentSession.attachedFiles || []).length) return
    if (isLoading) return

    const fileNames = (currentSession.attachedFiles || []).map((f) => f.filename).join(', ')

    const displayContent = fileNames
      ? `当前会话文件：[${fileNames}]。\n用户需求：${userInput || '请基于这些文件进行分析'}`
      : userInput

    await sendCustomMessage(displayContent, {
      clearInput: true
    })
  }

  const themeVars = {
    '--theme-primary': themeStyle.primary,
    '--theme-primary-dark': themeStyle.primaryDark,
    '--theme-primary-soft': themeStyle.primarySoft,
    '--theme-primary-border': themeStyle.primaryBorder,
    '--theme-ghost-bg': themeStyle.ghostBg,
    '--theme-text': themeStyle.text,
    '--theme-header-bg': themeStyle.headerBg,
    '--theme-light-panel': themeStyle.lightPanel,
    '--theme-sidebar-from': themeStyle.sidebarGradientFrom,
    '--theme-sidebar-to': themeStyle.sidebarGradientTo,
    '--theme-sidebar-text': themeStyle.sidebarText,
    '--theme-sidebar-muted': themeStyle.sidebarMuted,
    '--theme-lab-bg': themeStyle.labBg,
    '--theme-lab-text': themeStyle.labText,
    '--theme-shadow-soft': `${themeStyle.primary}18`,
    '--theme-shadow-strong': `${themeStyle.primary}2a`
  }

  return (
    <div className={`app-container app-theme-${currentTheme}`} style={themeVars}>
      <Sidebar
        sidebarWidth={sidebarWidth}
        sessions={sessions}
        currentSessionId={currentSessionId}
        themeStyle={themeStyle}
        onNewSession={handleNewSession}
        onSelectSession={handleSelectSession}
        onDeleteSession={handleDeleteSession}
      />

      <div className="resizer sidebar-resizer" onMouseDown={startResizeSidebar} />

      <ChatPanel
        leftWidth={leftWidth}
        currentSession={currentSession}
        currentTheme={currentTheme}
        currentAgentLabel={currentAgentLabel}
        themeStyle={themeStyle}
        isLoading={isLoading}
        loadingText={loadingText}
        userInput={userInput}
        setUserInput={setUserInput}
        sendMessage={sendMessage}
        fileInputRef={fileInputRef}
        handleFileUpload={handleFileUpload}
        inputPlaceholder={inputPlaceholder}
        uploadIcon={uploadIcon}
        handleAgentSwitch={handleAgentSwitch}
        normalizeToAbsoluteFileUrl={(url) => normalizeToAbsoluteFileUrl(url, API_BASE)}
        messagesEndRef={messagesEndRef}
      />

      <div className="resizer main-resizer" onMouseDown={startResizeChat} />

      <WorkbenchPanel
        currentSession={currentSession}
        themeStyle={themeStyle}
        handleDeleteUploadedFile={handleDeleteUploadedFile}
        isFileAlreadyAttached={isFileAlreadyAttached}
        getRelativePathFromUrl={(url) => getRelativePathFromUrl(url, API_BASE)}
        addResultToCurrentSession={addResultToCurrentSession}
      />
    </div>
  )
}

export default App
