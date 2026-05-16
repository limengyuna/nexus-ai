/** @type {import('tailwindcss').Config} */
export default {
  // class 策略：在 <html> 上加 'dark' class 即启用暗色模式
  darkMode: 'class',
  // 扫描这些文件中使用的 class，进行 tree-shaking
  content: [
    './index.html',
    './src/**/*.{vue,js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      // 项目主题色（后续可扩展）
      colors: {
        primary: {
          50: '#eef2ff',
          100: '#e0e7ff',
          500: '#6366f1',
          600: '#4f46e5',
          700: '#4338ca',
          900: '#312e81',
        },
      },
    },
  },
  plugins: [],
}
