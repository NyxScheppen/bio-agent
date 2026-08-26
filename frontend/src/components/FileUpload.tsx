import { useRef, type ChangeEvent } from 'react'
import { useUploadStore } from '../stores/uploadStore'

export default function FileUpload() {
  const inputRef = useRef<HTMLInputElement>(null)
  const uploading = useUploadStore((s) => s.uploading)
  const fileId = useUploadStore((s) => s.fileId)
  const upload = useUploadStore((s) => s.upload)

  const onChange = (e: ChangeEvent<HTMLInputElement>): void => {
    const file = e.target.files?.[0]
    if (file) void upload(file).catch(() => {})
  }

  return (
    <div className="p-4">
      <input ref={inputRef} type="file" onChange={onChange} className="hidden" />
      <button
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        className="px-4 py-2 rounded bg-gray-900 text-white text-sm disabled:opacity-50"
      >
        {uploading ? '上传中…' : '选择数据文件'}
      </button>
      {fileId && <span className="ml-2 text-xs text-gray-500">fileId: {fileId}</span>}
    </div>
  )
}
