<script setup lang="ts">
/**
 * 全局确认弹窗组件
 *
 * 由 useConfirm composable 触发，挂载在 App.vue 根层级
 * 替代浏览器原生 confirm() 弹窗
 */
import { onMounted, onUnmounted } from 'vue'
import { AlertTriangle, HelpCircle } from 'lucide-vue-next'

import { useConfirm } from '@/composables/useConfirm'

const { state, handleConfirm, handleCancel } = useConfirm()

// Esc 键关闭
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && state.value.open) {
    handleCancel()
  }
  if (e.key === 'Enter' && state.value.open) {
    handleConfirm()
  }
}

onMounted(() => window.addEventListener('keydown', onKeyDown))
onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <transition
    enter-active-class="transition-opacity duration-150"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition-opacity duration-100"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="state.open"
      class="fixed inset-0 bg-black/50 flex items-center justify-center z-[60]"
      @click.self="handleCancel"
    >
      <transition
        enter-active-class="transition-all duration-200 ease-out"
        enter-from-class="opacity-0 scale-95"
        enter-to-class="opacity-100 scale-100"
        appear
      >
        <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-[24rem] overflow-hidden">
          <!-- 头部：图标 + 标题 -->
          <div class="px-5 pt-5 pb-3 flex items-start gap-3">
            <div
              class="w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0"
              :class="state.variant === 'danger' ? 'bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400' : 'bg-blue-100 dark:bg-blue-900/40 text-blue-600 dark:text-blue-400'"
            >
              <AlertTriangle v-if="state.variant === 'danger'" :size="20" :stroke-width="2" />
              <HelpCircle v-else :size="20" :stroke-width="2" />
            </div>
            <div class="min-w-0 flex-1 pt-0.5">
              <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">{{ state.title }}</h3>
              <p class="text-sm text-gray-600 dark:text-gray-300 mt-1 leading-relaxed">{{ state.message }}</p>
            </div>
          </div>

          <!-- 按钮区 -->
          <div class="px-5 py-3 bg-gray-50 dark:bg-gray-800/50 flex justify-end gap-2">
            <button
              class="px-4 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
              @click="handleCancel"
            >
              {{ state.cancelText }}
            </button>
            <button
              class="px-4 py-1.5 text-sm font-medium text-white rounded-lg transition-colors"
              :class="state.variant === 'danger'
                ? 'bg-red-600 hover:bg-red-700'
                : 'bg-primary-600 hover:bg-primary-700'"
              @click="handleConfirm"
            >
              {{ state.confirmText }}
            </button>
          </div>
        </div>
      </transition>
    </div>
  </transition>
</template>
