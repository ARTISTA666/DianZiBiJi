import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "#d8dee8",
        surface: "#f7f9fb",
        ink: "#172033",
        muted: "#657084",
        brand: "#176b87",
        accent: "#2f8f6b",
        warning: "#b7791f",
      },
      boxShadow: {
        panel: "0 1px 2px rgba(23, 32, 51, 0.06), 0 8px 24px rgba(23, 32, 51, 0.04)",
      },
    },
  },
  plugins: [],
};

export default config;
