import type {
  Artifact,
  ChatResponse,
  HistoryResponse,
  Message,
  SessionSummary,
  UploadFileItem,
} from './types'

const JSON_HEADERS = { 'Content-Type': 'application/json' }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = body && typeof body === 'object' && 'detail' in body ? body.detail : null
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${response.status})`)
  }
  return body as T
}

export function fileUrl(relativePath: string): string {
  const path = relativePath.replace(/^\/+/, '')
  return `/files/${path.split('/').map(encodeURIComponent).join('/')}`
}

export function normalizeArtifact(raw: Record<string, unknown>): Artifact | null {
  const name = String(raw.name ?? raw.filename ?? '').trim()
  const relativePath = String(raw.relative_path ?? raw.relativePath ?? '').replace(/^\/+/, '')
  if (!name || !relativePath || !/^(uploads|generated)\//.test(relativePath)) return null
  return {
    name,
    relativePath,
    url: fileUrl(relativePath),
    type: String(raw.type ?? raw.file_type ?? 'other'),
    sizeBytes: typeof raw.size_bytes === 'number' ? raw.size_bytes : undefined,
    sourceType: typeof raw.source_type === 'string' ? raw.source_type : undefined,
  }
}

export function listSessions(): Promise<SessionSummary[]> {
  return request('/api/history')
}

export function getSession(sessionId: string): Promise<HistoryResponse> {
  return request(`/api/history/${encodeURIComponent(sessionId)}`)
}

export function deleteSession(sessionId: string): Promise<Record<string, unknown>> {
  return request(`/api/chat/session/${encodeURIComponent(sessionId)}`, { method: 'DELETE' })
}

export async function listUploads(sessionId: string): Promise<Artifact[]> {
  const data = await request<{ files: UploadFileItem[] }>(
    `/api/uploads/${encodeURIComponent(sessionId)}`,
  )
  return data.files
    .map((item) => normalizeArtifact(item as unknown as Record<string, unknown>))
    .filter((item): item is Artifact => item !== null)
}

export async function uploadFiles(sessionId: string, files: File[]): Promise<Artifact[]> {
  const form = new FormData()
  form.set('session_id', sessionId)
  files.forEach((file) => form.append('files', file))
  const data = await request<{ files: UploadFileItem[] }>('/api/upload', {
    method: 'POST',
    body: form,
  })
  return data.files
    .map((item) => normalizeArtifact(item as unknown as Record<string, unknown>))
    .filter((item): item is Artifact => item !== null)
}

export function deleteUpload(sessionId: string, filename: string): Promise<Record<string, unknown>> {
  return request(
    `/api/uploads/${encodeURIComponent(sessionId)}/${encodeURIComponent(filename)}`,
    { method: 'DELETE' },
  )
}

export function sendChat(
  sessionId: string,
  messages: Message[],
  attachedFiles: Artifact[],
): Promise<ChatResponse> {
  return request('/api/chat', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({
      session_id: sessionId,
      messages: messages.map(({ role, content }) => ({ role, content })),
      attached_files: attachedFiles.map((file) => ({
        filename: file.name,
        relative_path: file.relativePath,
        url: file.url,
        type: file.type,
        size_bytes: file.sizeBytes,
      })),
    }),
  })
}

export async function healthCheck(): Promise<boolean> {
  try {
    const result = await request<{ status: string }>('/api/health')
    return result.status === 'ok'
  } catch {
    return false
  }
}
