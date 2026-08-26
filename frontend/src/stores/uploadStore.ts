import { create } from 'zustand'
import * as client from '../api/client'

interface UploadState {
  uploading: boolean
  fileId: string | null
  upload: (file: File) => Promise<void>
}

export const useUploadStore = create<UploadState>((set) => ({
  uploading: false,
  fileId: null,

  upload: async (file: File): Promise<void> => {
    set({ uploading: true })
    try {
      const result = await client.upload(file)
      set({ fileId: result.fileId, uploading: false })
    } catch (err) {
      set({ uploading: false })
      throw err
    }
  },
}))
