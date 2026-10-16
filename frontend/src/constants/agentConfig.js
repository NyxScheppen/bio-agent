// Keep production builds same-origin while allowing a separate backend during
// local development or when the frontend is hosted independently.
export const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '')

export const AGENT_OPTIONS = [
  { key: 'bird', label: '🐦 小红', command: '切换到小红模式' },
  { key: 'fox', label: '🦊 小紫', command: '切换到小紫模式' },
  { key: 'lion', label: '🦁 小蓝', command: '切换到小蓝模式' },
  { key: 'snake', label: '🐍 小灰', command: '切换到小灰模式' }
]

export const AGENT_WELCOME_MESSAGES = {
  bird: '你好，我是小红，可以帮你完成常见生信分析、文件处理和结果整理。',
  fox: '你好，我是小紫。我会先检查数据，再尽量给出稳妥的分析结果。',
  lion: '你好，我是小蓝，可以协助你完成分析、建模和结果汇总。',
  snake: '你好，我是小灰。请尽量把目标、数据和需求说明清楚。'
}

export const AGENT_STATUS_MESSAGES = {
  bird: '请上传分析所需文件，我会先检查数据结构再开始处理。',
  fox: '支持上传 csv / tsv / txt / xlsx / rds 等文件，建议按任务准备完整输入。',
  lion: '如需差异分析、富集分析、生存分析或建模，请尽量一并上传相关文件。',
  snake: '建议上传完整输入文件，例如表达矩阵、分组表、生存表等。'
}

export const AGENT_LOADING_MESSAGES = {
  bird: '小红正在处理中',
  fox: '小紫正在处理中',
  lion: '小蓝正在处理中',
  snake: '小灰正在处理中'
}

export const AGENT_AVATARS = {
  bird: '🐦',
  fox: '🦊',
  lion: '🦁',
  snake: '🐍'
}

export const AGENT_UPLOAD_ICONS = {
  bird: '📁',
  fox: '📁',
  lion: '📁',
  snake: '📁'
}

export const AGENT_INPUT_PLACEHOLDERS = {
  bird: '输入分析需求… 左侧可上传多个文件',
  fox: '描述你的分析任务… 左侧可上传多个文件',
  lion: '请输入任务说明… 支持多文件联合分析',
  snake: '请清楚描述目标… 并上传相关输入文件'
}

export const THEME_STYLE_MAP = {
  bird: {
    primary: '#e85d75',
    primaryDark: '#c63f58',
    primarySoft: '#fdecef',
    primaryBorder: '#f4b6c2',
    ghostBg: '#fff5f7',
    text: '#7f1d1d',
    headerBg: '#fff1f4',
    lightPanel: '#fff8fa',
    sidebarGradientFrom: '#f0627d',
    sidebarGradientTo: '#d9465f',
    sidebarText: '#fff7f8',
    sidebarMuted: 'rgba(255,255,255,0.82)',
    labBg: '#e85d75',
    labText: '#ffffff'
  },
  fox: {
    primary: '#a855f7',
    primaryDark: '#9333ea',
    primarySoft: '#f5eefe',
    primaryBorder: '#dec4fb',
    ghostBg: '#faf5ff',
    text: '#6b21a8',
    headerBg: '#faf5ff',
    lightPanel: '#fcf8ff',
    sidebarGradientFrom: '#b26bf8',
    sidebarGradientTo: '#8b3ff0',
    sidebarText: '#fcf7ff',
    sidebarMuted: 'rgba(255,255,255,0.82)',
    labBg: '#a855f7',
    labText: '#ffffff'
  },
  lion: {
    primary: '#4f8ef7',
    primaryDark: '#2f6fdb',
    primarySoft: '#edf4ff',
    primaryBorder: '#bfd6ff',
    ghostBg: '#f5f9ff',
    text: '#163d7a',
    headerBg: '#f5f9ff',
    lightPanel: '#f9fbff',
    sidebarGradientFrom: '#5fa0ff',
    sidebarGradientTo: '#356fd6',
    sidebarText: '#f6fbff',
    sidebarMuted: 'rgba(255,255,255,0.82)',
    labBg: '#4f8ef7',
    labText: '#ffffff'
  },
  snake: {
    primary: '#6b7280',
    primaryDark: '#4b5563',
    primarySoft: '#eef1f5',
    primaryBorder: '#d5dbe3',
    ghostBg: '#f7f8fa',
    text: '#374151',
    headerBg: '#f8fafc',
    lightPanel: '#fbfcfd',
    sidebarGradientFrom: '#7c8594',
    sidebarGradientTo: '#5b6472',
    sidebarText: '#f8fafc',
    sidebarMuted: 'rgba(255,255,255,0.82)',
    labBg: '#6b7280',
    labText: '#ffffff'
  }
}
