/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cream: {
          50:  '#FAF9F5',
          100: '#F5F3ED',
          200: '#EFECE2',
          300: '#E3DFD1',
          400: '#C9C4B2',
        },
        ink: {
          900: '#1A1915',
          700: '#3D3A32',
          500: '#6B6855',
          400: '#8A8672',
        },
        clay: {
          500: '#D97757',
          600: '#C4654A',
          100: '#F4E4DB',
        },
        up:   { 500: '#2D8659', 100: '#D9EBE0' },
        down: { 500: '#C14D3F', 100: '#F4DCD8' },
        warn: { 500: '#C48A1E', 100: '#F4E8CE' },
        info: { 500: '#6B7FB8', 100: '#DDE3EE' },
      },
      fontFamily: {
        mono: ['SF Mono', 'Menlo', 'Consolas', 'monospace'],
        sans: ['-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
