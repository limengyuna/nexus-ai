<script setup lang="ts">
/**
 * 思考过程面板
 *
 * 展示最近一次回复的：
 * - Intent + 路由理由
 * - 命中的 Skill
 * - 工具调用详情
 * - RAG 检索结果（前几条，可展开完整内容）
 * - 执行链路时间线
 */
import { computed, ref } from 'vue'
import { Sparkles, Zap, Copy, Check } from 'lucide-vue-next'

import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

// 复制工具/Skill 调用的结果
const copiedIndex = ref<number | null>(null)

function copyToClipboard(text: string, index: number) {
  navigator.clipboard.writeText(text).then(() => {
    copiedIndex.value = index
    setTimeout(() => {
      copiedIndex.value = null
    }, 2000)
  }).catch((err) => {
    console.error('Failed to copy text: ', err)
  })
}

// RAG 片段展开状态（key 为索引）
const expandedDocs = ref<Set<number>>(new Set())

function toggleDoc(index: number) {
  if (expandedDocs.value.has(index)) {
    expandedDocs.value.delete(index)
  } else {
    expandedDocs.value.add(index)
  }
}

const hasData = computed(() =>
  chat.lastIntent || chat.lastTrace.length > 0 || chat.lastToolCalls.length > 0,
)

// 从 execution_trace 中提取每个节点的 token 消耗
const nodeTokens = computed(() => {
  return chat.lastTrace
    .filter((step: any) => step.output?.tokens)
    .map((step: any) => ({ node: step.node, tokens: step.output.tokens }))
})

// 本次回复总 token
const totalTokens = computed(() => {
  return nodeTokens.value.reduce((sum: number, item: any) => sum + item.tokens, 0)
})

// 会话累计 token
const sessionTotalTokens = computed(() => {
  return chat.messages
    .filter((m: any) => m.role === 'assistant' && m.token_usage)
    .reduce((sum: number, m: any) => sum + (m.token_usage || 0), 0)
})

function formatTokens(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

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
              <summary class="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 select-none">参数/结果</summary>
              <div class="relative group mt-1.5">
                <button
                  @click="copyToClipboard(formatArgs({ arguments: tc.arguments, result: tc.result }), i)"
                  class="absolute right-2 top-2 p-1.5 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 z-10"
                  title="复制参数和结果"
                >
                  <Check v-slot:default v-if="copiedIndex === i" :size="13" class="text-green-600 dark:text-green-400" />
                  <Copy v-slot:default v-else :size="13" />
                </button>
                <pre class="p-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded overflow-x-auto text-gray-700 dark:text-gray-200 pr-10 select-all">{{ formatArgs({ arguments: tc.arguments, result: tc.result }) }}</pre>
              </div>
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
            class="border rounded-lg p-2.5 cursor-pointer transition-colors"
            :class="doc.adopted !== false
              ? 'border-blue-200 dark:border-blue-800 bg-blue-50/40 dark:bg-blue-900/20 hover:bg-blue-50/70 dark:hover:bg-blue-900/30'
              : 'border-gray-200 dark:border-gray-700 bg-gray-50/40 dark:bg-gray-800/30 opacity-60 hover:opacity-80'"
            @click="toggleDoc(i)"
          >
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs font-medium" :class="doc.adopted !== false ? 'text-blue-700 dark:text-blue-300' : 'text-gray-500 dark:text-gray-400'">
                #{{ i + 1 }} {{ doc.metadata.file_name || '未知来源' }}
                <span v-if="doc.adopted === false" class="ml-1 text-gray-400 dark:text-gray-500">(未采用)</span>
              </span>
              <div class="flex items-center gap-2">
                <span class="text-xs" :class="doc.adopted !== false ? 'text-gray-500 dark:text-gray-400' : 'text-gray-400 dark:text-gray-500'">score={{ doc.score.toFixed(4) }}</span>
                <span class="text-xs text-gray-400 dark:text-gray-500 select-none">{{ expandedDocs.has(i) ? '▼' : '▶' }}</span>
              </div>
            </div>
            <p
              class="text-xs whitespace-pre-wrap break-words"
              :class="[
                doc.adopted !== false ? 'text-gray-700 dark:text-gray-300' : 'text-gray-500 dark:text-gray-400',
                { 'line-clamp-3': !expandedDocs.has(i) }
              ]"
            >{{ doc.content }}</p>
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
            <span v-if="step.output?.tokens" class="text-amber-600 dark:text-amber-400">{{ formatTokens(step.output.tokens) }} tokens</span>
            <span class="text-gray-400 dark:text-gray-500 ml-auto">{{ step.elapsed_ms }}ms</span>
          </div>
        </div>
      </section>

      <!-- Token 用量 -->
      <section v-if="totalTokens > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
          <Zap :size="13" class="text-amber-500" />
          Token 用量
        </div>
        <div class="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-amber-50/40 dark:bg-amber-900/10">
          <!-- 分节点明细 -->
          <div class="flex flex-wrap gap-x-4 gap-y-1 text-xs mb-2">
            <span
              v-for="item in nodeTokens"
              :key="item.node"
              class="text-gray-600 dark:text-gray-300"
            >
              <span class="font-mono font-medium">{{ item.node }}</span>:
              <span class="text-amber-700 dark:text-amber-300 font-semibold">{{ formatTokens(item.tokens) }}</span>
            </span>
          </div>
          <!-- 总计 -->
          <div class="flex items-center justify-between text-xs pt-2 border-t border-gray-200 dark:border-gray-700">
            <span class="text-gray-500 dark:text-gray-400">本次回复</span>
            <span class="font-semibold text-amber-700 dark:text-amber-300">{{ formatTokens(totalTokens) }} tokens</span>
          </div>
          <div v-if="sessionTotalTokens > 0" class="flex items-center justify-between text-xs mt-1">
            <span class="text-gray-500 dark:text-gray-400">会话累计</span>
            <span class="font-medium text-gray-600 dark:text-gray-300">{{ formatTokens(sessionTotalTokens) }} tokens</span>
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
