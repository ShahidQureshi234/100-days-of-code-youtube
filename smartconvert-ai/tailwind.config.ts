import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: {
          950: "#070b14",
          900: "#0b1120",
          800: "#111a2e",
          700: "#1a2540",
          600: "#24325a",
        },
        accent: {
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
        },
        cyanx: "#22d3ee",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 40px -12px rgba(99, 102, 241, 0.45)",
        card: "0 10px 30px -12px rgba(2, 6, 23, 0.85)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};

export default config;
