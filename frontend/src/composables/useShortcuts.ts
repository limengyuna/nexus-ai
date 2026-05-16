/**
 * 全局键盘快捷键 composable
 *
 * 在组件 setup 中调用 useShortcut('ctrl+k', () => ...) 即可注册。
 * 自动在组件卸载时清理事件监听。
 *
 * 支持的修饰键：ctrl / cmd / shift / alt
 * 在输入框 / textarea / contenteditable 内自动忽略（除非配置 allowInInputs=true）
 */
import { onMounted, onUnmounted } from 'vue'

export interface ShortcutOptions {
  /** 是否在输入框聚焦时也触发（默认 false，避免干扰打字）*/
  allowInInputs?: boolean
  /** 是否阻止默认行为（默认 true）*/
  preventDefault?: boolean
}

interface ParsedShortcut {
  key: string
  ctrl: boolean
  shift: boolean
  alt: boolean
  meta: boolean  // Cmd 键（Mac）或 Windows 键
}

/**
 * 把 "ctrl+k" / "cmd+shift+p" / "esc" 解析成结构化对象
 * cmd 在 Mac 上对应 metaKey，在 Windows 上自动等价于 ctrl
 */
function parseShortcut(combo: string): ParsedShortcut {
  const parts = combo.toLowerCase().split('+').map((p) => p.trim())
  const result: ParsedShortcut = {
    key: '',
    ctrl: false,
    shift: false,
    alt: false,
    meta: false,
  }
  for (const part of parts) {
    if (part === 'ctrl') result.ctrl = true
    else if (part === 'shift') result.shift = true
    else if (part === 'alt') result.alt = true
    else if (part === 'cmd' || part === 'meta') result.meta = true
    else result.key = part
  }
  return result
}

/**
 * 判断当前焦点是否在可输入元素中
 */
function isInputElement(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  if (el.isContentEditable) return true
  return false
}

/**
 * 注册一个键盘快捷键
 *
 * @example
 * useShortcut('ctrl+k', () => openCommandPalette())
 * useShortcut('esc', () => closeModal(), { allowInInputs: true })
 */
export function useShortcut(
  combo: string,
  handler: (e: KeyboardEvent) => void,
  options: ShortcutOptions = {},
) {
  const { allowInInputs = false, preventDefault = true } = options
  const parsed = parseShortcut(combo)

  function onKeyDown(e: KeyboardEvent) {
    // 在输入元素中通常应该让快捷键失效（避免干扰打字）
    if (!allowInInputs && isInputElement(e.target)) return

    // 跨平台：在 Mac 上 cmd=meta；在 Win/Linux 上 cmd 也接受 ctrl
    const isMac = navigator.platform.toLowerCase().includes('mac')
    const ctrlPressed = isMac ? e.metaKey : e.ctrlKey
    const metaPressed = isMac ? e.metaKey : e.ctrlKey

    // ctrl 修饰要求
    if (parsed.ctrl && !ctrlPressed) return
    if (!parsed.ctrl && !parsed.meta && (e.ctrlKey || e.metaKey)) {
      // 如果用户没要求 ctrl/meta，但实际按了，则不触发（避免冲突浏览器快捷键）
      return
    }
    if (parsed.meta && !metaPressed) return
    if (parsed.shift !== e.shiftKey) return
    if (parsed.alt !== e.altKey) return

    // 按键名匹配（不区分大小写）
    if (e.key.toLowerCase() !== parsed.key) return

    if (preventDefault) e.preventDefault()
    handler(e)
  }

  onMounted(() => window.addEventListener('keydown', onKeyDown))
  onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
}
