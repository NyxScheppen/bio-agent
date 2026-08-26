import type { ExecutedStep, Step, TaskDetail, TaskSummary, ToolMeta, UploadResult } from '../types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, init)
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}: ${path}`)
  }
  return (await resp.json()) as T
}

export async function listTasks(): Promise<TaskSummary[]> {
  const rows = await request<Array<Record<string, unknown>>>('/tasks')
  return rows.map(toTaskSummary)
}

export async function getTask(id: string): Promise<TaskDetail> {
  const row = await request<Record<string, unknown>>(`/tasks/${id}`)
  return toTaskDetail(row)
}

export async function upload(file: File): Promise<UploadResult> {
  const form = new FormData()
  form.append('file', file)
  const row = await request<Record<string, unknown>>('/uploads', { method: 'POST', body: form })
  return {
    fileId: row.file_id as string,
    originalName: row.original_name as string,
    size: row.size as number,
  }
}

export async function listTools(): Promise<ToolMeta[]> {
  return request<ToolMeta[]>('/tools')
}

// snake_case → camelCase 唯一转换点
function toTaskSummary(row: Record<string, unknown>): TaskSummary {
  return {
    id: row.id as string,
    userMessage: row.user_message as string,
    status: row.status as string,
    createdAt: row.created_at as number,
    updatedAt: row.updated_at as number,
  }
}

function toTaskDetail(row: Record<string, unknown>): TaskDetail {
  return {
    ...toTaskSummary(row),
    plan: (row.plan as Step[]) ?? [],
    steps: (row.steps as ExecutedStep[]) ?? [],
    report: (row.report as string) ?? '',
    error: (row.error as string | null) ?? null,
  }
}
