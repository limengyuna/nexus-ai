<script setup lang="ts">
import { computed, ref } from 'vue'
import { Sparkles, Clock, ChevronDown, ChevronRight } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

// 决策历史展开状态
const expandedDecisions = ref(false)

// 决策历史：倒序展示（最新一条放最上面），且过滤掉当前最新的（在卡片上方已展示）
const previousDecisions = computed(() => {
  const list = chat.lastDecisions || []
  if (list.length <= 1) return []
  return list.slice(0, -1).reverse()
})

function decisionIntentClass(intent: string) {
  if (intent === 'rag') return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
  if (intent === 'tool') return 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'
  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
}

const taskPlan = computed(() => chat.lastTaskPlan || [])
const hasTaskPlan = computed(() => taskPlan.value.length > 0)
const completedSteps = computed(() => taskPlan.value.filter((s: any) => s.status === 'completed').length)
const totalSteps = computed(() => taskPlan.value.length)
</script>

<template>
  <section class="rounded-[16px] bg-white dark:bg-[#121319] p-5 shadow-[0_2px_8px_rgba(0,0,0,0.04)] dark:shadow-none ring-1 ring-black/[0.03] dark:ring-white/[0.04]">
    <div class="flex items-center justify-between mb-4">
      <span class="text-xs font-bold text-zinc-500 dark:text-zinc-400 flex items-center gap-2">
        <Sparkles :size="14" class="text-zinc-700 dark:text-zinc-300" />
        Supervisor 决策
      </span>
      <span v-if="chat.lastIntent" class="px-2.5 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-widest"
        :class="{
          'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400': chat.lastIntent === 'rag',
          'bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400': chat.lastIntent === 'tool',
          'bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400': chat.lastIntent === 'chitchat',
        }"
      >{{ chat.lastIntent }}</span>
    </div>
    
    <div v-if="chat.lastRouteReason" class="flex items-center justify-between mb-2">
      <span class="text-xs font-medium text-zinc-500 dark:text-zinc-400 shrink-0">计划概述</span>
      <p class="text-xs text-zinc-700 dark:text-zinc-300 text-right truncate pl-4" :title="chat.lastRouteReason">
        {{ chat.lastRouteReason }}
      </p>
    </div>

    <!-- 决策历史折叠（仅当存在多条历史决策时显示） -->
    <div v-if="previousDecisions.length > 0" class="mt-3 pt-2.5 border-t border-gray-100 dark:border-gray-800">
      <div
        class="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
        @click="expandedDecisions = !expandedDecisions"
      >
        <component :is="expandedDecisions ? ChevronDown : ChevronRight" :size="11" />
        <Clock :size="11" class="text-primary-500" />
        <span>历史决策（{{ previousDecisions.length }} 条）</span>
      </div>
      <div v-if="expandedDecisions" class="mt-2 space-y-1.5 animate-slide-down">
        <div
          v-for="(d, idx) in previousDecisions"
          :key="idx"
          class="rounded-lg border border-gray-100 dark:border-gray-800 bg-white dark:bg-gray-900/40 p-2.5"
        >
          <div class="flex items-center justify-between mb-1">
            <span class="text-[10px] font-mono text-gray-400 dark:text-gray-500">#{{ previousDecisions.length - idx }}</span>
            <span
              v-if="d.intent"
              class="px-1.5 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider"
              :class="decisionIntentClass(d.intent)"
            >{{ d.intent }}</span>
          </div>
          <p class="text-[11px] text-gray-600 dark:text-gray-300 leading-relaxed">
            {{ d.routeReason }}
          </p>
        </div>
      </div>
    </div>

    <!-- 进度条与执行数据 -->
    <div v-if="hasTaskPlan" class="mt-4 pt-4 border-t border-gray-100 dark:border-gray-800/60 space-y-3">
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-zinc-500 dark:text-zinc-400">总体进度</span>
        <div class="flex items-center gap-3 w-1/2 justify-end">
          <div class="w-24 h-1.5 bg-blue-100 dark:bg-blue-900/30 rounded-full overflow-hidden">
            <div
              class="h-full bg-blue-600 dark:bg-blue-500 rounded-full transition-all duration-700 ease-out"
              :style="{ width: totalSteps > 0 ? `${(completedSteps / totalSteps) * 100}%` : '0%' }"
            ></div>
          </div>
          <span class="text-[11px] font-mono font-bold text-zinc-700 dark:text-zinc-300">
            {{ totalSteps > 0 ? Math.round((completedSteps / totalSteps) * 100) : 0 }}%
          </span>
        </div>
      </div>
      <div class="flex items-center justify-between">
        <span class="text-xs font-medium text-zinc-500 dark:text-zinc-400">决策时间</span>
        <span class="text-xs font-mono text-zinc-700 dark:text-zinc-300">{{ chat.lastTrace.length > 0 ? chat.lastTrace[0].elapsed_ms : 0 }}ms</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
@keyframes slide-down {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-slide-down {
  animation: slide-down 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
</style>
