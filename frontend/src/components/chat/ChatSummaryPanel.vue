<script setup lang="ts">
import { FileText, Zap } from 'lucide-vue-next'

defineProps<{
  summary: string
  createdAt: string
  updatedAt: string
  totalTokens: number
}>()

function formatLocalTime(utcStr: string | undefined | null): string {
  if (!utcStr) return ''
  const d = new Date(utcStr)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  })
}

function formatTokens(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<template>
  <div class="px-5 py-3.5 bg-amber-500/5 border-b border-amber-200/40 dark:border-amber-900/20 overflow-hidden">
    <div class="flex items-start gap-2.5">
      <FileText :size="13" class="text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
      <div class="min-w-0 flex-1">
        <div class="text-[9px] font-bold text-amber-600/80 dark:text-amber-400/80 uppercase tracking-widest mb-1 font-outfit">AI MEMORY KEYWORDS</div>
        <p class="text-xs text-gray-600 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{{ summary }}</p>
        <div class="mt-2.5 flex items-center gap-3 text-[9px] text-gray-400 dark:text-gray-500 font-medium">
          <span>创建时间：{{ formatLocalTime(createdAt) }}</span>
          <span>更新时间：{{ formatLocalTime(updatedAt) }}</span>
          <span v-if="totalTokens > 0" class="flex items-center gap-0.5 text-amber-600 dark:text-amber-400 font-semibold bg-amber-500/10 px-1.5 py-0.5 rounded">
            <Zap :size="9" />
            累计吞吐 {{ formatTokens(totalTokens) }} tokens
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
