/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "../app/templates/**/*.html",
    "../app/static/js/**/*.js",
    "../app/template_filters.py"
  ],
  safelist: [
    // Sentiment badge colors (dynamically generated in Python)
    'bg-green-300', 'bg-green-400', 'bg-green-500',
    'bg-red-300', 'bg-red-400', 'bg-red-500',
    'bg-gray-400',
    'text-white', 'text-green-900', 'text-red-900',
    'text-green-300', 'text-green-400', 'text-green-500',
    'text-red-300', 'text-red-400', 'text-red-500',
    'text-gray-400',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
    },
  },
  plugins: [
    require("@tailwindcss/typography"),
    require("daisyui")
  ],
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
