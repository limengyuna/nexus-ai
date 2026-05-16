/**
 * 全局确认弹窗 composable
 *
 * 替代浏览器原生 confirm() —— 提供 Promise 风格 API + 自定义样式
 *
 * 用法：
 *   const ok = await confirm({ title: '删除确认', message: '...' })
 *   if (!ok) return
 */
import { ref } from 'vue'

export type ConfirmVariant = 'default' | 'danger'

export interface ConfirmOptions {
  title: string
  message: string
  confirmText?: string
  cancelText?: string
  variant?: ConfirmVariant  // danger 用红色按钮（适合删除场景）
}

interface InternalState extends ConfirmOptions {
  open: boolean
  resolve?: (value: boolean) => void
}

// 模块级单例，所有调用点共享同一个弹窗
const state = ref<InternalState>({
  open: false,
  title: '',
  message: '',
})

export function useConfirm() {
  /**
   * 弹出确认框，返回 Promise<boolean>
   * true = 用户点击「确定」；false = 取消
   */
  function confirm(options: ConfirmOptions): Promise<boolean> {
    return new Promise((resolve) => {
      state.value = {
        open: true,
        title: options.title,
        message: options.message,
        confirmText: options.confirmText ?? '确定',
        cancelText: options.cancelText ?? '取消',
        variant: options.variant ?? 'default',
        resolve,
      }
    })
  }

  function handleConfirm() {
    state.value.resolve?.(true)
    state.value.open = false
  }

  function handleCancel() {
    state.value.resolve?.(false)
    state.value.open = false
  }

  return { state, confirm, handleConfirm, handleCancel }
}
