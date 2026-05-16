<script setup lang="ts">
/**
 * 思考过程面板
 *
 * 展示最近一次回复的：
 * - Intent + 路由理由
 * - 命中的 Skill
 * - 工具调用详情
 * - RAG 检索结果（前几条）
 * - 执行链路时间线
 */
import { computed } from 'vue'
import { Sparkles } from 'lucide-vue-next'

import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

const hasData = computed(() =>
  chat.lastIntent || chat.lastTrace.length > 0 || chat.lastToolCalls.length > 0,
)

function formatArgs(args: any): string {
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args)
  }
}

function intentColor(intent: string): string {
  if (intent === 'rag') return 'bg-blue-100 text-blue-700'
  if (intent === 'tool') return 'bg-purple-100 text-purple-700'
  if (intent === 'chitchat') return 'bg-gray-100 text-gray-700'
  return 'bg-gray-100 text-gray-500'
}
</script>

<template>
  <div class="h-full overflow-y-auto bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-800">
    <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
        <Sparkles :size="16" :stroke-width="2" class="text-primary-600 dark:text-primary-400" />
        <span>思考过程</span>
      </h3>
      <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">展示 Agent 的完整推理链路</p>
    </div>

    <div v-if="!hasData" class="px-5 py-12 text-center text-sm text-gray-400 dark:text-gray-500">
      发一条消息开始对话<br>右侧将展示 Agent 的思考过程
    </div>

    <div v-else class="px-5 py-4 space-y-5 text-sm">
      <!-- Intent 决策 -->
      <section>
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">ROUTER 决策</div>
        <div class="flex items-center gap-2 mb-1.5">
          <span class="px-2 py-0.5 rounded text-xs font-medium" :class="intentColor(chat.lastIntent)">
            {{ chat.lastIntent || '—' }}
          </span>
          <span v-if="chat.lastSkillUsed" class="px-2 py-0.5 rounded bg-emerald-100 text-emerald-700 text-xs font-medium">
            Skill: {{ chat.lastSkillUsed }}
          </span>
        </div>
        <p v-if="chat.lastRouteReason" class="text-xs text-gray-600 dark:text-gray-400 italic">"{{ chat.lastRouteReason }}"</p>
      </section>

      <!-- 工具调用 -->
      <section v-if="chat.lastToolCalls.length > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
          工具调用 <span class="text-gray-400 dark:text-gray-500">({{ chat.lastToolCalls.length }} 次)</span>
        </div>
        <div class="space-y-2">
          <div
            v-for="(tc, i) in chat.lastToolCalls"
            :key="i"
            class="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-800"
          >
            <div class="flex items-center justify-between mb-1.5">
              <span class="font-mono text-xs font-semibold text-purple-700 dark:text-purple-300">{{ tc.name }}</span>
              <span class="text-xs text-gray-400 dark:text-gray-500">{{ tc.kind }}</span>
            </div>
            <details class="text-xs">
              <summary class="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">参数/结果</summary>
              <pre class="mt-1.5 p-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded overflow-x-auto text-gray-700 dark:text-gray-200">{{ formatArgs({ arguments: tc.arguments, result: tc.result }) }}</pre>
            </details>
          </div>
        </div>
      </section>

      <!-- RAG 检索结果 -->
      <section v-if="chat.lastRetrievedDocs.length > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">
          RAG 检索 <span class="text-gray-400 dark:text-gray-500">({{ chat.lastRetrievedDocs.length }} 段)</span>
        </div>
        <div class="space-y-2">
          <div
            v-for="(doc, i) in chat.lastRetrievedDocs.slice(0, 5)"
            :key="i"
            class="border border-gray-200 dark:border-gray-700 rounded-lg p-2.5 bg-blue-50/40 dark:bg-blue-900/20"
          >
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs font-medium text-blue-700 dark:text-blue-300">#{{ i + 1 }} {{ doc.metadata.file_name || '未知来源' }}</span>
              <span class="text-xs text-gray-500 dark:text-gray-400">score={{ doc.score.toFixed(4) }}</span>
            </div>
            <p class="text-xs text-gray-700 dark:text-gray-300 line-clamp-3">{{ doc.content }}</p>
          </div>
        </div>
      </section>

      <!-- 执行链路时间线 -->
      <section v-if="chat.lastTrace.length > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2">执行链路</div>
        <div class="space-y-1.5">
          <div
            v-for="(step, i) in chat.lastTrace"
            :key="i"
            class="flex items-center gap-2 text-xs"
          >
            <span class="w-1.5 h-1.5 rounded-full bg-primary-500"></span>
            <span class="font-mono font-medium text-gray-700 dark:text-gray-200">{{ step.node }}</span>
            <span class="text-gray-400 dark:text-gray-500 ml-auto">{{ step.elapsed_ms }}ms</span>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
