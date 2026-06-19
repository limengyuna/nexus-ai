<script setup lang="ts">
import { Clock } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
</script>

<template>
  <section v-if="chat.lastTrace.length > 0">
    <div class="text-xs font-bold tracking-widest text-zinc-500 dark:text-zinc-400 mb-4 flex items-center gap-2 uppercase">
      <Clock :size="14" class="text-zinc-400 dark:text-zinc-500" />
      执行链路耗时
    </div>
    <div class="bg-white dark:bg-[#121319] p-5 rounded-[16px] shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:shadow-none ring-1 ring-black/[0.03] dark:ring-white/[0.04]">
      <div class="relative pl-4 border-l border-zinc-200 dark:border-zinc-800/60 ml-2 space-y-5">
        <div
          v-for="(step, i) in chat.lastTrace"
          :key="i"
          class="relative flex items-center gap-3 text-xs"
        >
          <div class="absolute -left-[21px] w-2.5 h-2.5 rounded-full ring-2 ring-white dark:ring-[#121319] flex items-center justify-center" :class="step.node === 'rag_agent' || step.node === 'business_context_agent' ? 'bg-emerald-500' : 'bg-slate-400 dark:bg-slate-600'"></div>
          <span class="font-mono font-medium text-slate-700 dark:text-slate-200 min-w-[120px]">{{ step.node }}</span>
          <span class="font-mono text-slate-400 dark:text-slate-500 ml-auto">{{ step.elapsed_ms }}ms</span>
        </div>
      </div>
    </div>
  </section>
</template>
