/**
 * Legal Metrology Mobile - Design System Tokens
 * Exact extraction from Stitch Tailwind Configuration
 */

export const colors = {
  // Primary Palette
  primary: '#031635',
  primaryContainer: '#1a2b4b',
  onPrimary: '#ffffff',
  onPrimaryContainer: '#8293b8',
  primaryFixed: '#d8e2ff',
  primaryFixedDim: '#b6c6ef',

  // Surface & Background Palette
  surface: '#f8f9ff',
  surfaceBright: '#f8f9ff',
  surfaceDim: '#d8dae0',
  surfaceContainerLowest: '#ffffff',
  surfaceContainerLow: '#f2f3f9',
  surfaceContainer: '#eceef3',
  surfaceContainerHigh: '#e7e8ee',
  surfaceContainerHighest: '#e1e2e8',
  surfaceVariant: '#e1e2e8',
  background: '#f8f9ff',

  // Text & Content Palette
  onSurface: '#191c20',
  onSurfaceVariant: '#44474e',
  onBackground: '#191c20',

  // Secondary & Borders
  secondary: '#585f66',
  secondaryContainer: '#dae0e9',
  onSecondary: '#ffffff',
  onSecondaryContainer: '#5c636a',
  borderSubtle: '#c5c6cf',
  outline: '#75777f',
  outlineVariant: '#c5c6cf',

  // Statutory Status Colors
  statusGreenBg: '#e8f5e9',
  statusGreenText: '#1b5e20',
  statusRedBg: '#ffebee',
  statusRedText: '#b71c1c',
  statusAmberBg: '#fff3e0',
  statusAmberText: '#e65100',

  // Error Palette
  error: '#ba1a1a',
  errorContainer: '#ffdad6',
  onError: '#ffffff',
  onErrorContainer: '#93000a',
};

export const spacing = {
  tight: 4,
  base: 8,
  stackSm: 8,
  stackMd: 12,
  gutter: 16,
  marginX: 16,
  stackLg: 20,
  stackXl: 24,
};

export const borderRadius = {
  default: 2,
  DEFAULT: 2,
  sm: 2,
  lg: 4,
  xl: 8,
  full: 12,
  round: 9999,
};

export const typography = {
  caption: {
    fontSize: 12,
    lineHeight: 16,
    fontWeight: '400' as const,
    color: colors.onSurfaceVariant,
  },
  labelCaps: {
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.24, // 0.02em
    fontWeight: '600' as const,
    textTransform: 'uppercase' as const,
    color: colors.onSurfaceVariant,
  },
  bodySm: {
    fontSize: 13,
    lineHeight: 18,
    fontWeight: '400' as const,
    color: colors.onSurfaceVariant,
  },
  bodyMd: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '400' as const,
    color: colors.onSurface,
  },
  bodyMdMedium: {
    fontSize: 14,
    lineHeight: 20,
    fontWeight: '500' as const,
    color: colors.onSurface,
  },
  sectionHeader: {
    fontSize: 16,
    lineHeight: 24,
    fontWeight: '600' as const,
    color: colors.primary,
  },
  headlineLg: {
    fontSize: 20,
    lineHeight: 28,
    fontWeight: '600' as const,
    color: colors.primary,
  },
};
