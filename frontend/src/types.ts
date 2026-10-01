export type MessageRole = 'user' | 'assistant'

export interface Message {
  id: string
  role: MessageRole
  content: string
  files?: Artifact[]
}

export interface Artifact {
  name: string
  relativePath: string
  url: string
  type: string
  sizeBytes?: number
  sourceType?: string
}

export interface SessionSummary {
  session_id: string
  title: string
  created_at: string
  message_count: number
  file_count: number
}

export interface HistoryResponse {
  session_id: string
  messages: Array<{ role: string; content: string; created_at: string }>
  files: Array<{
    filename: string
    relative_path: string
    file_type?: string
    source_type?: string
  }>
}

export interface UploadFileItem {
  filename: string
  relative_path: string
  url?: string
  type?: string
  size_bytes?: number
}

export interface ChatResponse {
  reply: string
  files?: Array<Record<string, unknown>>
  session_id: string
  title: string
}
