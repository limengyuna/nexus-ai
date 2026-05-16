/**
 * 主题（亮/暗）切换 composable
 *
 * - 状态持久化到 localStorage
 * - 初始化时优先 localStorage，其次 prefers-color-scheme，最后默认 light
 * - 通过给 <html> 加/移 `.dark` class 触发 tailwind dark: 样式
 */
import { ref, watch } from 'vue'

export type ThemeMode = 'light' | 'dark'

const STORAGE_KEY = 'nexusai_theme'

// 模块级单例：所有组件共享同一份主题状态
const theme = ref<ThemeMode>(detectInitialTheme())

function detectInitialTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'light'
  const stored = localStorage.getItem(STORAGE_KEY) as ThemeMode | null
  if (stored === 'light' || stored === 'dark') return stored
  // 跟随系统偏好（首次访问）
  if (window.matchMedia?.('(prefers-color-scheme: dark)').matches) return 'dark'
  return 'light'
}

function applyTheme(mode: ThemeMode) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  if (mode === 'dark') {
    root.classList.add('dark')
  } else {
    root.classList.remove('dark')
  }
  // 同步 color-scheme，让原生滚动条/表单也跟随
  root.style.colorScheme = mode
}

// 监听变化：写 localStorage + 应用到 DOM
watch(
  theme,
  (val) => {
    localStorage.setItem(STORAGE_KEY, val)
    applyTheme(val)
  },
  { immediate: true },
)

export function useTheme() {
  function toggle() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  function set(mode: ThemeMode) {
    theme.value = mode
  }

  return { theme, toggle, set }
}
