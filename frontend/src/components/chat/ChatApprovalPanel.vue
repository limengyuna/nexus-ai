<script setup lang="ts">
import type { InterruptEvent } from '@/api/chat'

defineProps<{
  approval: InterruptEvent
  sending: boolean
}>()

const emit = defineEmits<{
  (e: 'approve'): void
  (e: 'reject'): void
}>()
</script>

<template>
  <div class="mx-6 mb-4 rounded-md bg-amber-50/80 dark:bg-amber-950/20 shadow-sm border border-amber-300/60 dark:border-amber-600/30 overflow-hidden animate-pulse-subtle">
    <!-- 标题 -->
    <div class="flex items-center gap-2 px-4 py-3 bg-amber-100/50 dark:bg-amber-900/20 border-b border-amber-200/40 dark:border-amber-900/20">
      <span class="text-amber-500 text-base">⚠️</span>
      <span class="text-xs font-bold text-amber-800 dark:text-amber-300">Agent 请求执行敏感工具</span>
      <span class="ml-auto text-[9px] px-2 py-0.5 rounded-full bg-amber-200/60 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 font-bold uppercase tracking-wider font-outfit">
        {{ (approval.payload as any).tool_kind }}
      </span>
    </div>
    <!-- 内容 -->
    <div class="px-4 py-3 space-y-2.5">
      <div class="text-xs font-semibold text-gray-700 dark:text-gray-200">
        <span>{{ approval.payload.message }}</span>
      </div>
      <div class="text-[10px] text-gray-500 dark:text-gray-400 font-medium">
        调用工具：<code class="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded font-mono text-[9px] font-bold text-gray-700 dark:text-gray-300">{{ (approval.payload as any).tool_name }}</code>
      </div>
      <!-- 参数 -->
      <details class="text-[10px] font-semibold">
        <summary class="cursor-pointer text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">查看参数详情</summary>
        <pre class="mt-1.5 p-2 bg-gray-100/50 dark:bg-gray-900/50 border border-gray-200/30 dark:border-gray-800/30 rounded-sm text-[9px] font-mono overflow-x-auto max-h-32 text-gray-600 dark:text-gray-400">{{ JSON.stringify((approval.payload as any).arguments, null, 2) }}</pre>
      </details>
    </div>
    <!-- 按钮 -->
    <div class="flex items-center gap-3 px-4 py-3 border-t border-amber-200/40 dark:border-amber-900/20 bg-amber-50/20 dark:bg-amber-900/10">
      <button
        class="flex-1 py-1.5 text-xs font-bold rounded-sm bg-green-600 hover:bg-green-700 text-white transition-all shadow-md shadow-green-600/10 active:scale-[0.98] disabled:opacity-60"
        :disabled="sending"
        @click="$emit('approve')"
      >
        ✓ 批准执行
      </button>
      <button
        class="flex-1 py-1.5 text-xs font-bold rounded-sm bg-red-50 dark:bg-red-950/20 hover:bg-red-100 dark:hover:bg-red-900/40 text-red-700 dark:text-red-400 border border-red-200/40 dark:border-red-900/30 transition-all active:scale-[0.98] disabled:opacity-60"
        :disabled="sending"
        @click="$emit('reject')"
      >
        ✗ 拒绝执行
      </button>
    </div>
  </div>
</template>
