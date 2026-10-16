import { getPrimaryButtonStyle, getSecondaryButtonStyle } from '../../utils/themeHelpers'

function ThemeButton({
  variant = 'primary',
  disabled = false,
  themeStyle,
  onClick,
  children,
  style = {},
  ...props
}) {
  const baseStyle =
    variant === 'secondary'
      ? getSecondaryButtonStyle(themeStyle, disabled)
      : getPrimaryButtonStyle(themeStyle, disabled)

  return (
    <button onClick={onClick} disabled={disabled} style={{ ...baseStyle, ...style }} {...props}>
      {children}
    </button>
  )
}

export default ThemeButton