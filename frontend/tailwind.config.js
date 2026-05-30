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
          50: '#faf9f5', // 极致纯净的暖纸白
          100: '#f3f0e8', // 温润燕麦白
          500: '#c8b3a0', // 经典浅砂褐
          600: '#bda590', // 中沙褐
          700: '#9c8470', // 深砂褐
          900: '#4a3e3d', // 泥炭黑褐
        },
      },
    },
  },
  plugins: [],
}
