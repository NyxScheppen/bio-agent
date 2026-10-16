export const normalizeToAbsoluteFileUrl = (url, apiBase) => {
  if (!url) return ''

  let finalUrl = String(url).trim()

  if (!finalUrl) return ''

  finalUrl = finalUrl.replace(/\\/g, '/')

  if (finalUrl.startsWith('http://') || finalUrl.startsWith('https://')) {
    return finalUrl.replace('/workspace/', '/files/')
  }

  if (finalUrl.startsWith('/files/')) {
    return `${apiBase}${finalUrl}`
  }

  if (finalUrl.startsWith('generated/')) {
    return `${apiBase}/files/${finalUrl}`
  }

  if (finalUrl.startsWith('uploads/')) {
    return `${apiBase}/files/${finalUrl}`
  }

  if (finalUrl.startsWith('files/')) {
    return `${apiBase}/${finalUrl}`
  }

  finalUrl = finalUrl.replace(/^\/+/, '')
  return `${apiBase}/files/${finalUrl}`
}

export const getRelativePathFromUrl = (url, apiBase) => {
  if (!url) return ''

  const str = String(url).split('?')[0].replace(/\\/g, '/')

  if (str.startsWith('/files/')) {
    return str.replace('/files/', '')
  }

  if (apiBase && str.startsWith(`${apiBase}/files/`)) {
    return str.replace(`${apiBase}/files/`, '')
  }

  const filesIndex = str.indexOf('/files/')
  if (filesIndex >= 0) {
    return str.slice(filesIndex + '/files/'.length)
  }

  if (str.startsWith('generated/') || str.startsWith('uploads/')) {
    return str
  }

  return str.replace(/^\/+/, '')
}

const normalizeFilename = (value) => {
  if (!value) return ''
  return String(value).split('?')[0].replace(/\\/g, '/').split('/').pop() || ''
}

export const isImagePath = (value) => {
  if (!value) return false
  return /\.(png|jpg|jpeg|svg|gif|webp)(\?|$)/i.test(String(value))
}

export const isPdfPath = (value) => {
  if (!value) return false
  return /\.pdf(\?|$)/i.test(String(value))
}

export const isKnownDownloadablePath = (value) => {
  if (!value) return false
  return /\.(png|jpg|jpeg|svg|gif|webp|pdf|csv|tsv|txt|xlsx|xls|json|zip|rds|rdata)(\?|$)/i.test(
    String(value)
  )
}

export const getCanonicalResultKey = (item, apiBase = '') => {
  if (!item) return ''

  const relativePath =
    item.relativePath ||
    item.relative_path ||
    getRelativePathFromUrl(item.rawUrl || item.content || item.url || '', apiBase)

  if (relativePath) {
    return `path:${String(relativePath).split('?')[0].replace(/^\/+/, '')}`
  }

  const raw = item.rawUrl || item.content || item.url || ''
  if (raw) {
    return `url:${String(raw).split('?')[0]}`
  }

  const filename = normalizeFilename(item.filename || item.name || item.title)
  if (filename) {
    return `name:${filename}`
  }

  return ''
}

export const guessResultType = (file) => {
  if (!file) return 'file'

  const filename = file.filename || file.name || ''
  const url = file.url || file.rawUrl || file.content || ''
  const relativePath = file.relative_path || file.relativePath || ''

  if (file.type === 'image') return 'plot'
  if (file.fileType === 'image') return 'plot'

  if (isImagePath(filename)) return 'plot'
  if (isImagePath(url)) return 'plot'
  if (isImagePath(relativePath)) return 'plot'

  return 'file'
}

export const buildResultFromFile = (file, apiBase) => {
  const relativePath = file.relative_path || file.relativePath || ''
  const filename = file.filename || file.name || normalizeFilename(relativePath) || 'download'

  const absoluteUrl = normalizeToAbsoluteFileUrl(
    file.url || relativePath || file.name || file.filename,
    apiBase
  )

  const resultType = guessResultType({
    ...file,
    filename,
    relativePath,
    url: absoluteUrl
  })

  return {
    id: `${relativePath || filename}_${Date.now()}_${Math.random()}`,
    type: resultType,
    fileType: resultType === 'plot' ? 'image' : file.type || 'other',
    title: resultType === 'plot' ? `📊 ${filename}` : `📄 ${filename}`,
    content: resultType === 'plot' ? `${absoluteUrl}?t=${Date.now()}` : absoluteUrl,
    rawUrl: absoluteUrl,
    filename,
    relativePath,
    sourceType: file.source_type || file.sourceType || 'generated'
  }
}

export const mergeSessionResults = (session, incomingResults, apiBase = '') => {
  const prevResults = session.results || []
  const allResults = [...(incomingResults || []), ...prevResults]
  const resultMap = new Map()

  allResults.forEach((item) => {
    const key = getCanonicalResultKey(item, apiBase)

    if (!key) {
      resultMap.set(`fallback:${item.id || Math.random()}`, item)
      return
    }

    const existing = resultMap.get(key)

    if (!existing) {
      resultMap.set(key, item)
      return
    }

    const existingHasPath =
      existing.relativePath ||
      existing.relative_path ||
      getRelativePathFromUrl(existing.rawUrl || existing.content || existing.url || '', apiBase)

    const currentHasPath =
      item.relativePath ||
      item.relative_path ||
      getRelativePathFromUrl(item.rawUrl || item.content || item.url || '', apiBase)

    const existingIsBackend = existing.sourceType === 'generated' && !!existingHasPath
    const currentIsBackend = item.sourceType === 'generated' && !!currentHasPath

    if (!existingIsBackend && currentIsBackend) {
      resultMap.set(key, item)
    }
  })

  return Array.from(resultMap.values())
}

export const isFileAlreadyAttached = (session, targetFile) => {
  const attached = session?.attachedFiles || []
  return attached.some((f) => {
    const a = f.relative_path || f.relativePath || f.url || f.filename
    const b =
      targetFile.relative_path ||
      targetFile.relativePath ||
      targetFile.url ||
      targetFile.filename

    return a === b
  })
}