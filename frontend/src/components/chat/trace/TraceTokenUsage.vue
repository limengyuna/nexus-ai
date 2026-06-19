<script setup lang="ts">
import { computed } from 'vue'
import { Zap } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

const nodeTokens = computed(() => {
  return chat.lastTrace
    .filter((step: any) => step.output?.tokens)
    .map((step: any) => ({ node: step.node, tokens: step.output.tokens }))
})

const totalTokens = computed(() => nodeTokens.value.reduce((sum: number, item: any) => sum + item.tokens, 0))

const sessionTotalTokens = computed(() => {
  return chat.messages
    .filter((m: any) => m.role === 'assistant' && m.token_usage)
    .reduce((sum: number, m: any) => sum + (m.token_usage || 0), 0)
})

function formatTokens(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<template>
  <section v-if="totalTokens > 0">
    <div class="text-xs font-bold tracking-widest text-zinc-500 dark:text-zinc-400 mb-4 flex items-center gap-2 uppercase">
      <Zap :size="14" class="text-zinc-400 dark:text-zinc-500" />
      Token 用量
    </div>
    <div class="bg-white dark:bg-[#121319] p-5 rounded-[16px] shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:shadow-none ring-1 ring-black/[0.03] dark:ring-white/[0.04]">
      
      <div class="grid grid-cols-2 gap-4 mb-6">
        <div class="bg-zinc-50/50 dark:bg-zinc-900/30 p-3 rounded-xl ring-1 ring-zinc-200/50 dark:ring-zinc-800/50">
          <div class="text-[10px] font-medium text-zinc-500 dark:text-zinc-400 mb-1">本次消耗</div>
          <div class="flex items-baseline gap-1">
            <span class="text-lg font-bold font-mono text-zinc-900 dark:text-white">{{ formatTokens(totalTokens) }}</span>
            <span class="text-[10px] text-zinc-400 font-medium">tokens</span>
          </div>
        </div>
        <div class="bg-zinc-50/50 dark:bg-zinc-900/30 p-3 rounded-xl ring-1 ring-zinc-200/50 dark:ring-zinc-800/50">
          <div class="text-[10px] font-medium text-zinc-500 dark:text-zinc-400 mb-1">累计会话</div>
          <div class="flex items-baseline gap-1">
            <span class="text-lg font-bold font-mono text-zinc-800 dark:text-zinc-200">{{ formatTokens(sessionTotalTokens) }}</span>
            <span class="text-[10px] text-zinc-400 font-medium">tokens</span>
          </div>
        </div>
      </div>

      <div class="space-y-3 mb-5">
        <div v-for="item in nodeTokens" :key="item.node" class="flex items-center justify-between text-xs">
          <div class="flex items-center gap-2.5">
            <span class="w-1.5 h-1.5 rounded-full" :class="item.node === 'supervisor' ? 'bg-blue-500' : (item.node === 'rag_agent' ? 'bg-emerald-500' : 'bg-orange-500')"></span>
            <span class="font-mono text-zinc-600 dark:text-zinc-400">{{ item.node }}</span>
          </div>
          <span class="font-mono font-medium text-zinc-700 dark:text-zinc-300">{{ formatTokens(item.tokens) }}</span>
        </div>
      </div>
      
      <div class="flex items-center gap-3 pt-4 border-t border-zinc-100 dark:border-zinc-800/60">
        <span class="text-[10px] font-medium text-zinc-500">上下文占用</span>
        <div class="flex-1 h-1.5 bg-zinc-100 dark:bg-zinc-800 rounded-full overflow-hidden">
          <div class="h-full bg-blue-500 rounded-full" style="width: 23%"></div>
        </div>
        <span class="text-[10px] font-mono text-zinc-500">23%</span>
      </div>
    </div>
  </section>
</template>
