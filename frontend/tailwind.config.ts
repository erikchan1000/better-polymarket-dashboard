import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Dark-first surface palette.
        surface: {
          950: "#0a0b0f",
          900: "#0f1117",
          800: "#161923",
          700: "#1e222e",
          600: "#2a2f3d",
        },
        accent: {
          DEFAULT: "#6366f1",
          soft: "#818cf8",
        },
        buy: "#22c55e",
        sell: "#ef4444",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
