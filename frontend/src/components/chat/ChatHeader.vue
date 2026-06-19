<script setup lang="ts">
import { ChevronDown, ChevronLeft, ChevronRight, FileText, Library, PanelLeftClose, PanelLeftOpen, Sparkles } from 'lucide-vue-next'

defineProps<{
  sidebarCollapsed: boolean
  sessionTitle: string
  activeKbName: string | null
  hasSummary: boolean
  showSummary: boolean
  showThinking: boolean
}>()

defineEmits<{
  (e: 'toggle-sidebar'): void
  (e: 'toggle-summary'): void
  (e: 'toggle-thinking'): void
}>()
</script>

<template>
  <div class="h-14 px-5 bg-white dark:bg-zinc-950 border-b border-gray-100/60 dark:border-gray-800/30 flex items-center justify-between flex-shrink-0 z-20 transition-colors">
    <div class="flex items-center gap-2.5 min-w-0">
      <!-- 侧边栏按钮 -->
      <button
        class="p-1.5 rounded-sm text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100/80 dark:hover:bg-gray-800/40 transition-all flex-shrink-0 active:scale-95"
        :title="sidebarCollapsed ? '展开会话列表' : '收起会话列表'"
        @click="$emit('toggle-sidebar')"
      >
        <PanelLeftOpen v-if="sidebarCollapsed" :size="16" :stroke-width="2.5" />
        <PanelLeftClose v-else :size="16" :stroke-width="2.5" />
      </button>

      <div class="text-xs font-bold text-gray-700 dark:text-gray-200 truncate">
        {{ sessionTitle }}
      </div>

      <div v-if="activeKbName" class="text-[10px] bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 px-2 py-0.5 rounded-full border border-zinc-200 dark:border-zinc-700 flex items-center gap-1 font-semibold">
        <Library :size="10" :stroke-width="2.5" />
        <span>知识库：{{ activeKbName }}</span>
      </div>
    </div>

    <div class="flex items-center gap-2">
      <!-- 对话摘要按钮 -->
      <button
        v-if="hasSummary"
        class="px-2.5 py-1.5 rounded-md text-[10px] font-bold flex items-center gap-1 transition-colors border shadow-xs"
        :class="showSummary
          ? 'bg-zinc-100 border-zinc-200 text-zinc-800 dark:bg-zinc-800 dark:border-zinc-700 dark:text-zinc-200 hover:bg-zinc-200 dark:hover:bg-zinc-700'
          : 'bg-white dark:bg-gray-900 border-gray-200/50 dark:border-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'"
        title="查看 AI 对当前对话的理解摘要"
        @click="$emit('toggle-summary')"
      >
        <FileText :size="12" :stroke-width="2.5" />
        <span>对话摘要</span>
        <ChevronDown :size="12" class="transition-transform duration-200" :class="showSummary ? 'rotate-180' : ''" />
      </button>

      <!-- 思考过程按钮 -->
      <button
        class="px-2.5 py-1.5 rounded-md text-[10px] font-bold flex items-center gap-1 transition-colors border shadow-xs"
        :class="showThinking
          ? 'bg-zinc-1000/10 border-zinc-300 dark:border-zinc-700 text-zinc-900 dark:text-zinc-100 hover:bg-zinc-1000/20'
          : 'bg-white dark:bg-gray-900 border-gray-200/50 dark:border-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'"
        :title="showThinking ? '隐藏思考过程' : '查看 Agent 完整推理链路'"
        @click="$emit('toggle-thinking')"
      >
        <Sparkles :size="12" :stroke-width="2.5" />
        <span>思考过程</span>
        <component :is="showThinking ? ChevronRight : ChevronLeft" :size="12" class="text-gray-400" />
      </button>
    </div>
  </div>
</template>
