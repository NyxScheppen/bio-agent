export const getPrimaryButtonStyle = (themeStyle, disabled = false) => ({
  border: 'none',
  borderRadius: '10px',
  padding: '8px 12px',
  cursor: disabled ? 'not-allowed' : 'pointer',
  background: disabled ? '#d1d5db' : themeStyle.primary,
  color: disabled ? '#4b5563' : '#ffffff',
  fontWeight: 700,
  transition: 'all 0.2s ease',
  opacity: disabled ? 0.8 : 1
})

export const getSecondaryButtonStyle = (themeStyle, disabled = false) => ({
  border: `1px solid ${themeStyle.primaryBorder}`,
  borderRadius: '10px',
  padding: '8px 12px',
  cursor: disabled ? 'not-allowed' : 'pointer',
  background: disabled ? '#f3f4f6' : themeStyle.primarySoft,
  color: disabled ? '#6b7280' : themeStyle.text,
  fontWeight: 600,
  transition: 'all 0.2s ease',
  opacity: disabled ? 0.85 : 1
})

export const getDangerButtonStyle = (themeStyle) => ({
  minWidth: '32px',
  height: '32px',
  borderRadius: '50%',
  border: 'none',
  cursor: 'pointer',
  fontSize: '18px',
  fontWeight: 700,
  lineHeight: 1,
  background: themeStyle.primarySoft,
  color: themeStyle.primary
})

export const getSourceBadgeStyle = (themeStyle, isGenerated) => ({
  display: 'inline-flex',
  alignItems: 'center',
  padding: '2px 8px',
  borderRadius: '999px',
  fontSize: '12px',
  fontWeight: 700,
  background: isGenerated ? themeStyle.primarySoft : themeStyle.ghostBg,
  color: isGenerated ? themeStyle.primary : themeStyle.text,
  border: `1px solid ${themeStyle.primaryBorder}`
})