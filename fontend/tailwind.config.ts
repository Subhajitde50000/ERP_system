import type { Config } from "tailwindcss";

/**
 * shikshasync.me ERP + LMS design tokens — login_page_design.md §3, §12
 * Every brand colour lives here so all 15 modules stay consistent.
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "#E2E8F0",
        input: "#E2E8F0",
        ring: "#4F46E5",
        background: "#F8FAFC",
        foreground: "#0F172A",
        card: {
          DEFAULT: "#FFFFFF",
          foreground: "#0F172A",
        },
        primary: {
          DEFAULT: "#0F172A", // Slate 900
          foreground: "#F8FAFC",
        },
        accent: {
          DEFAULT: "#4F46E5", // Indigo 600
          hover: "#4338CA", // Indigo 700
          active: "#3730A3", // Indigo 800
          light: "#EEF2FF", // Indigo 50
          border: "#C7D2FE", // Indigo 200
          soft: "#818CF8", // Indigo 400
          foreground: "#FFFFFF",
        },
        secondary: {
          DEFAULT: "#06B6D4", // Cyan 500
          light: "#ECFEFF", // Cyan 50
          // Readable on white and on `light` — the brand cyan is 2.43:1 and
          // fails WCAG AA as text. Use DEFAULT for fills/icons, `text` for text.
          text: "#0E7490",
        },
        muted: {
          DEFAULT: "#F1F5F9",
          foreground: "#64748B",
        },
        destructive: {
          DEFAULT: "#EF4444",
          light: "#FEF2F2",
          border: "#FECACA",
          text: "#B91C1C", // 6.47:1 on white — DEFAULT is only 3.76:1
        },
        success: {
          DEFAULT: "#10B981",
          light: "#ECFDF5",
          text: "#047857", // 5.48:1 on white — DEFAULT is only 2.54:1
        },
        warning: {
          DEFAULT: "#F59E0B",
          light: "#FFFBEB",
          // Amber 200, matching `destructive.border` — a tinted callout needs
          // a border a shade darker than its fill or it reads as a flat block
          border: "#FDE68A",
          text: "#B45309", // 5.02:1 on white — DEFAULT is only 2.15:1
        },
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        display: ["var(--font-jakarta)", "var(--font-inter)", "sans-serif"],
      },
      borderRadius: {
        card: "16px",
        field: "10px",
      },
      boxShadow: {
        card: "0 4px 24px rgba(15, 23, 42, 0.06)",
        accent: "0 4px 14px rgba(79, 70, 229, 0.25)",
      },
      ringWidth: {
        3: "3px",
      },
      keyframes: {
        "fade-up": {
          from: { opacity: "0", transform: "translateY(8px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        shake: {
          "0%, 100%": { transform: "translateX(0)" },
          "20%, 60%": { transform: "translateX(-4px)" },
          "40%, 80%": { transform: "translateX(4px)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.4s ease-out both",
        shake: "shake 0.4s ease-in-out",
      },
    },
  },
  plugins: [],
};

export default config;
