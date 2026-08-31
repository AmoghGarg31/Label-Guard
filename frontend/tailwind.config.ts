import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./components/**/*.{ts,tsx}', './app/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f3f6f4', ink: '#10252a', navy: '#071b20', mint: '#63f1cb',
      },
      boxShadow: {
        panel: '0 8px 28px rgba(7,27,32,.06)', glow: '0 0 28px rgba(99,241,203,.22)',
      },
    },
  },
  plugins: [],
};
export default config;
