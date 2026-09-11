/**
 * shikshasync.me ERP + LMS design tokens — ported 1:1 from fontend/tailwind.config.ts
 * so the mobile app renders the exact same palette, radii and shadows as
 * the website. Every brand colour lives here so all modules stay consistent.
 */

export const Colors = {
  border: "#E2E8F0",
  input: "#E2E8F0",
  ring: "#4F46E5",
  background: "#F8FAFC",
  foreground: "#0F172A",
  card: "#FFFFFF",
  cardForeground: "#0F172A",
  primary: "#0F172A", // Slate 900
  primaryForeground: "#F8FAFC",
  accent: "#4F46E5", // Indigo 600
  accentHover: "#4338CA", // Indigo 700
  accentActive: "#3730A3", // Indigo 800
  accentLight: "#EEF2FF", // Indigo 50
  accentBorder: "#C7D2FE", // Indigo 200
  accentSoft: "#818CF8", // Indigo 400
  accentForeground: "#FFFFFF",
  secondary: "#06B6D4", // Cyan 500
  secondaryLight: "#ECFEFF", // Cyan 50
  secondaryText: "#0E7490",
  muted: "#F1F5F9",
  mutedForeground: "#64748B",
  destructive: "#EF4444",
  destructiveLight: "#FEF2F2",
  destructiveBorder: "#FECACA",
  destructiveText: "#B91C1C",
  success: "#10B981",
  successLight: "#ECFDF5",
  // The website never defines `success.border`, so `border-success-border`
  // falls back to the base border colour — keep the rendered result identical.
  successBorder: "#E2E8F0",
  successText: "#047857",
  warning: "#F59E0B",
  warningLight: "#FFFBEB",
  warningBorder: "#FDE68A",
  warningText: "#B45309",
  // Placeholders / auth form literals used by the website
  placeholder: "#94A3B8",
  labelText: "#334155",
  bodyText: "#475569",
  // Amber accents used by the team workspace (tailwind amber-50/600/700)
  amber50: "#FFFBEB",
  amber600: "#D97706",
  amber700: "#B45309",
} as const;

export const Radius = {
  card: 16, // rounded-card
  field: 10, // rounded-field
} as const;

export const Shadow = {
  card: {
    shadowColor: "#0F172A",
    shadowOpacity: 0.06,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  accent: {
    shadowColor: "#4F46E5",
    shadowOpacity: 0.25,
    shadowRadius: 7,
    shadowOffset: { width: 0, height: 4 },
    elevation: 3,
  },
} as const;

/** The website's font stacks are local-first (Inter → system-ui); on the
 * phone that resolves to the system font, so no bundled font is needed. */
export const Fonts = {
  sans: undefined as string | undefined,
  display: undefined as string | undefined,
} as const;
