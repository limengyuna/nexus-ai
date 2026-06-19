<script setup lang="ts">
/**
 * 思考过程面板 — 壳组件
 */
import { computed } from 'vue'
import { Brain } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'

import TraceSupervisorDecision from './chat/trace/TraceSupervisorDecision.vue'
import TracePlanSteps from './chat/trace/TracePlanSteps.vue'
import TraceMemoryInjection from './chat/trace/TraceMemoryInjection.vue'
import TraceExecutionTimeline from './chat/trace/TraceExecutionTimeline.vue'
import TraceTokenUsage from './chat/trace/TraceTokenUsage.vue'

const chat = useChatStore()

const hasData = computed(() =>
  chat.lastIntent || chat.lastTrace.length > 0 || chat.lastToolCalls.length > 0 || chat.lastTaskPlan.length > 0
)
</script>

<template>
  <div class="h-full overflow-y-auto bg-zinc-50/50 dark:bg-zinc-900/30 border-l border-zinc-200 dark:border-zinc-800/50">
    <!-- 标题栏 -->
    <div class="px-6 py-5 bg-zinc-50/90 dark:bg-[#09090b]/90 backdrop-blur-md sticky top-0 z-20 shadow-[0_1px_2px_rgba(0,0,0,0.02)] dark:shadow-none">
      <h3 class="text-base font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-2.5">
        <div class="p-1.5">
          <Brain :size="18" :stroke-width="2.5" class="text-zinc-900 dark:text-white" />
        </div>
        <span>思考过程</span>
      </h3>
      <p class="text-[11px] text-zinc-500 dark:text-zinc-400 mt-0.5 ml-9">Agent 的完整推理链路与上下文</p>
    </div>

    <!-- 空状态 -->
    <div v-if="!hasData" class="px-6 py-16 text-center text-sm text-zinc-400 dark:text-zinc-500">
      发一条消息开始对话<br>右侧将展示 Agent 的思考过程
    </div>

    <div v-else class="px-6 py-5 space-y-6 text-sm">
      <TraceSupervisorDecision />
      <TracePlanSteps />
      <TraceMemoryInjection />
      <TraceExecutionTimeline />
      <TraceTokenUsage />
    </div>
  </div>
</template>
