/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "Menlo", "monospace"],
      },
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        destructive: { DEFAULT: "hsl(var(--destructive))", foreground: "hsl(var(--destructive-foreground))" },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        // MyE brand semantics — addressed as `mye-*`
        mye: {
          primary: "hsl(var(--mye-primary))",
          "primary-soft": "hsl(var(--mye-primary-soft))",
          accent: "hsl(var(--mye-accent))",
          "accent-soft": "hsl(var(--mye-accent-soft))",
          surface: "hsl(var(--mye-bg-surface))",
          app: "hsl(var(--mye-bg-app))",
          sidebar: "hsl(var(--mye-sidebar))",
          ink: "hsl(var(--mye-ink))",
          "ink-muted": "hsl(var(--mye-ink-muted))",
          border: "hsl(var(--mye-border))",
        },
        status: {
          pending: "hsl(var(--status-pending))",
          active: "hsl(var(--status-active))",
          waiting: "hsl(var(--status-waiting))",
          escalated: "hsl(var(--status-escalated))",
          resolved: "hsl(var(--status-resolved))",
          closed: "hsl(var(--status-closed))",
          claim: "hsl(var(--status-claim))",
        },
      },
      keyframes: {
        "fade-in": { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "translateY(0)" } },
      },
      animation: {
        "fade-in": "fade-in 360ms cubic-bezier(0.22,1,0.36,1) both",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
