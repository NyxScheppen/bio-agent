import { fireEvent, render, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import FileUpload from './FileUpload'
import { useUploadStore } from '../stores/uploadStore'
import * as client from '../api/client'

vi.mock('../api/client', () => ({
  upload: vi.fn(),
}))

describe('FileUpload', () => {
  beforeEach(() => {
    useUploadStore.setState({ uploading: false, fileId: null })
    vi.mocked(client.upload).mockReset()
  })

  it('选文件 → upload → fileId', async () => {
    vi.mocked(client.upload).mockResolvedValue({ fileId: 'f1', originalName: 'a.tsv', size: 10 })
    const { container } = render(<FileUpload />)
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['x'], 'a.tsv', { type: 'text/tab-separated-values' })

    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => {
      expect(useUploadStore.getState().fileId).toBe('f1')
    })
    expect(client.upload).toHaveBeenCalledWith(file)
  })
})
