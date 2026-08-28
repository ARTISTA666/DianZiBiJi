import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
  	extend: {
  		colors: {
  			border: "hsl(var(--border))",
  			input: "hsl(var(--input))",
  			ring: "hsl(var(--ring))",
  			background: "hsl(var(--background))",
  			foreground: "hsl(var(--foreground))",
  			primary: {
  				DEFAULT: "hsl(var(--primary))",
  				foreground: "hsl(var(--primary-foreground))",
  			},
  			secondary: {
  				DEFAULT: "hsl(var(--secondary))",
  				foreground: "hsl(var(--secondary-foreground))",
  			},
  			destructive: {
  				DEFAULT: "hsl(var(--destructive))",
  				foreground: "hsl(var(--destructive-foreground))",
  			},
  			success: {
  				DEFAULT: "hsl(var(--success))",
  				foreground: "hsl(var(--success-foreground))",
  			},
  			warning: {
  				DEFAULT: "hsl(var(--warning))",
  				foreground: "hsl(var(--warning-foreground))",
  			},
  			info: {
  				DEFAULT: "hsl(var(--info))",
  				foreground: "hsl(var(--info-foreground))",
  			},
  			muted: {
  				DEFAULT: "hsl(var(--muted))",
  				foreground: "hsl(var(--muted-foreground))",
  			},
  			accent: {
  				DEFAULT: "hsl(var(--accent))",
  				foreground: "hsl(var(--accent-foreground))",
  			},
  			popover: {
  				DEFAULT: "hsl(var(--popover))",
  				foreground: "hsl(var(--popover-foreground))",
  			},
  			card: {
  				DEFAULT: "hsl(var(--card))",
  				foreground: "hsl(var(--card-foreground))",
  			},
  			sidebar: {
  				DEFAULT: "hsl(var(--sidebar-background))",
  				foreground: "hsl(var(--sidebar-foreground))",
  				primary: "hsl(var(--sidebar-primary))",
  				"primary-foreground": "hsl(var(--sidebar-primary-foreground))",
  				accent: "hsl(var(--sidebar-accent))",
  				"accent-foreground": "hsl(var(--sidebar-accent-foreground))",
  				border: "hsl(var(--sidebar-border))",
  				ring: "hsl(var(--sidebar-ring))",
  			},
  			chart: {
  				"1": "hsl(var(--chart-1))",
  				"2": "hsl(var(--chart-2))",
  				"3": "hsl(var(--chart-3))",
  				"4": "hsl(var(--chart-4))",
  				"5": "hsl(var(--chart-5))",
  			},
  		},
  		borderRadius: {
  			lg: "var(--radius)",
  			md: "calc(var(--radius) - 2px)",
  			sm: "calc(var(--radius) - 4px)",
  		},
  		fontFamily: {
  			sans: ["var(--font-sans)"],
  		},
  		boxShadow: {
  			subtle: "0 1px 2px 0 rgba(0, 0, 0, 0.04), 0 1px 3px 0 rgba(0, 0, 0, 0.03)",
  			card: "0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 2px 8px -2px rgba(0, 0, 0, 0.06)",
  			"card-hover": "0 4px 14px -2px rgba(0, 0, 0, 0.08), 0 2px 6px -1px rgba(0, 0, 0, 0.04)",
  			elevate: "0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.04)",
  			"glow-primary": "0 0 20px -5px hsl(var(--primary) / 0.35)",
  		},
  		keyframes: {
  			"accordion-down": {
  				from: { height: "0" },
  				to: { height: "var(--radix-accordion-content-height)" },
  			},
  			"accordion-up": {
  				from: { height: "var(--radix-accordion-content-height)" },
  				to: { height: "0" },
  			},
  			shimmer: {
  				"100%": {
  					transform: "translateX(100%)",
  				},
  			},
  			pulseSlow: {
  				"0%, 100%": { opacity: "1" },
  				"50%": { opacity: "0.5" },
  			},
  		},
  		animation: {
  			"accordion-down": "accordion-down 0.2s ease-out",
  			"accordion-up": "accordion-up 0.2s ease-out",
  			shimmer: "shimmer 2s infinite",
  			"pulse-slow": "pulseSlow 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
  		},
  	}
  },
  plugins: [tailwindcssAnimate],
};

export default config;
