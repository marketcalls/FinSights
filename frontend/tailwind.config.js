/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "../app/templates/**/*.html",
    "../app/static/js/**/*.js"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        light: {
          "primary": "#2563eb",
          "primary-content": "#ffffff",
          "secondary": "#64748b",
          "secondary-content": "#ffffff",
          "accent": "#0ea5e9",
          "accent-content": "#ffffff",
          "neutral": "#1f2937",
          "neutral-content": "#ffffff",
          "base-100": "#ffffff",
          "base-200": "#f8fafc",
          "base-300": "#e2e8f0",
          "base-content": "#1e293b",
          "info": "#3b82f6",
          "success": "#22c55e",
          "warning": "#f59e0b",
          "error": "#ef4444",
        },
      },
      "dark"
    ],
    darkTheme: "dark",
    base: true,
    styled: true,
    utils: true,
  },
}
