import { describe, expect, it } from 'vitest'
import { fileUrl, normalizeArtifact } from './api'

describe('artifact URL contract', () => {
  it('encodes each path component and keeps the same-origin files route', () => {
    expect(fileUrl('generated/session one/结果图.png')).toBe(
      '/files/generated/session%20one/%E7%BB%93%E6%9E%9C%E5%9B%BE.png',
    )
  })

  it('normalizes backend upload and generated file shapes', () => {
    expect(
      normalizeArtifact({
        filename: 'table.csv',
        relative_path: 'uploads/s1/table.csv',
        file_type: 'table',
      }),
    ).toMatchObject({ name: 'table.csv', type: 'table', url: '/files/uploads/s1/table.csv' })
  })

  it('rejects paths outside managed storage roots', () => {
    expect(normalizeArtifact({ name: 'secret', relative_path: '../secret' })).toBeNull()
  })
})
