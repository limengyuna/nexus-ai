<script setup lang="ts">
/**
 * 思考过程面板 — Task Pipeline 视图
 *
 * 展示 Supervisor 的任务拆解和分步执行进度：
 * 1. 顶部：Supervisor 决策摘要（intent + 计划概述）
 * 2. 核心：Task Plan 进度管道（步骤卡片 + 状态动画）
 * 3. 详情：工具调用 / RAG 检索（按步骤归类）
 * 4. 底部：执行链路时间线 + Token 用量
 */
import { computed, ref } from 'vue'
import {
  Sparkles, Zap, Copy, Check, CircleCheck, Circle, Loader,
  BookOpen, Wrench, ChevronDown, ChevronRight, Clock, Brain
} from 'lucide-vue-next'

import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

// 复制
const copiedIndex = ref<number | null>(null)
function copyToClipboard(text: string, index: number) {
  navigator.clipboard.writeText(text).then(() => {
    copiedIndex.value = index
    setTimeout(() => { copiedIndex.value = null }, 2000)
  }).catch((err) => console.error('Failed to copy:', err))
}

// RAG 片段展开
const expandedDocs = ref<Set<number>>(new Set())
function toggleDoc(index: number) {
  expandedDocs.value.has(index) ? expandedDocs.value.delete(index) : expandedDocs.value.add(index)
}

// 工具调用展开
const expandedTools = ref(false)

const hasData = computed(() =>
  chat.lastIntent || chat.lastTrace.length > 0 || chat.lastToolCalls.length > 0 || chat.lastTaskPlan.length > 0,
)

// Task Plan
const taskPlan = computed(() => chat.lastTaskPlan || [])
const hasTaskPlan = computed(() => taskPlan.value.length > 0)
const completedSteps = computed(() => taskPlan.value.filter((s: any) => s.status === 'completed').length)
const totalSteps = computed(() => taskPlan.value.length)

// Token 统计
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

function formatArgs(args: any): string {
  try { return JSON.stringify(args, null, 2) }
  catch { return String(args) }
}

function stepStatusIcon(status: string) {
  if (status === 'completed') return CircleCheck
  if (status === 'in_progress') return Loader
  return Circle
}

function stepStatusColor(status: string) {
  if (status === 'completed') return 'text-emerald-500'
  if (status === 'in_progress') return 'text-primary-500 animate-spin'
  return 'text-gray-300 dark:text-gray-600'
}

function agentIcon(agent: string) {
  return agent === 'rag_agent' ? BookOpen : Wrench
}

function agentLabel(agent: string) {
  return agent === 'rag_agent' ? 'RAG Agent' : 'Tool Agent'
}

function agentBadgeClass(agent: string) {
  return agent === 'rag_agent'
    ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300'
    : 'bg-purple-50 text-purple-600 dark:bg-purple-900/30 dark:text-purple-300'
}
</script>

<template>
  <div class="h-full overflow-y-auto bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-800">
    <!-- 标题栏 -->
    <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800">
      <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
        <Brain :size="16" :stroke-width="2" class="text-primary-600 dark:text-primary-400" />
        <span>思考过程</span>
      </h3>
      <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">展示 Agent 的完整推理链路</p>
    </div>

    <!-- 空状态 -->
    <div v-if="!hasData" class="px-5 py-12 text-center text-sm text-gray-400 dark:text-gray-500">
      发一条消息开始对话<br>右侧将展示 Agent 的思考过程
    </div>

    <div v-else class="px-5 py-4 space-y-4 text-sm">

      <!-- ========== Supervisor 决策摘要 ========== -->
      <section class="rounded-xl border border-gray-100 dark:border-gray-800 bg-gradient-to-br from-gray-50 to-white dark:from-gray-800/50 dark:to-gray-900 p-4">
        <div class="flex items-center justify-between mb-2">
          <span class="text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase tracking-wide">Supervisor 决策</span>
          <span v-if="chat.lastIntent" class="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider"
            :class="{
              'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300': chat.lastIntent === 'rag',
              'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300': chat.lastIntent === 'tool',
              'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300': chat.lastIntent === 'chitchat',
            }"
          >{{ chat.lastIntent }}</span>
        </div>
        <p v-if="chat.lastRouteReason" class="text-xs text-gray-600 dark:text-gray-300 leading-relaxed">
          {{ chat.lastRouteReason }}
        </p>
        <!-- 计划概览 -->
        <div v-if="hasTaskPlan" class="mt-3 flex items-center gap-2">
          <div class="flex-1 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
            <div
              class="h-full bg-gradient-to-r from-primary-400 to-emerald-400 rounded-full transition-all duration-700 ease-out"
              :style="{ width: totalSteps > 0 ? `${(completedSteps / totalSteps) * 100}%` : '0%' }"
            ></div>
          </div>
          <span class="text-[10px] font-mono text-gray-500 dark:text-gray-400 whitespace-nowrap">
            {{ completedSteps }}/{{ totalSteps }}
          </span>
        </div>
      </section>

      <!-- ========== Task Plan 管道 ========== -->
      <section v-if="hasTaskPlan">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3 flex items-center gap-1.5">
          <Sparkles :size="12" />
          执行计划
        </div>
        <div class="relative">
          <!-- 连接线 -->
          <div class="absolute left-[15px] top-4 bottom-4 w-px bg-gray-200 dark:bg-gray-700"></div>

          <div class="space-y-0">
            <div
              v-for="(step, i) in taskPlan"
              :key="i"
              class="relative pl-9 pb-4 last:pb-0"
            >
              <!-- 状态图标 -->
              <div class="absolute left-0 top-0.5 w-[30px] flex justify-center">
                <component
                  :is="stepStatusIcon(step.status)"
                  :size="16"
                  :stroke-width="2.5"
                  :class="stepStatusColor(step.status)"
                />
              </div>

              <!-- 步骤卡片 -->
              <div
                class="rounded-lg border p-3 transition-all duration-200"
                :class="{
                  'border-emerald-200 bg-emerald-50/50 dark:border-emerald-800 dark:bg-emerald-900/10': step.status === 'completed',
                  'border-primary-200 bg-primary-50/50 dark:border-primary-800 dark:bg-primary-900/10 ring-1 ring-primary-100 dark:ring-primary-900': step.status === 'in_progress',
                  'border-gray-200 bg-gray-50/50 dark:border-gray-700 dark:bg-gray-800/30': step.status === 'pending',
                }"
              >
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-[10px] font-mono font-bold text-gray-400 dark:text-gray-500">STEP {{ step.step }}</span>
                  <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium" :class="agentBadgeClass(step.agent)">
                    <component :is="agentIcon(step.agent)" :size="10" />
                    {{ agentLabel(step.agent) }}
                  </span>
                  <span v-if="step.status === 'completed'" class="ml-auto text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">✓ 完成</span>
                  <span v-else-if="step.status === 'in_progress'" class="ml-auto text-[10px] text-primary-600 dark:text-primary-400 font-medium">执行中...</span>
                </div>
                <p class="text-xs text-gray-600 dark:text-gray-300 leading-relaxed">
                  {{ step.instruction }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ========== 工具调用 ========== -->
      <section v-if="chat.lastToolCalls.length > 0">
        <div
          class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5 cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
          @click="expandedTools = !expandedTools"
        >
          <component :is="expandedTools ? ChevronDown : ChevronRight" :size="12" />
          <Wrench :size="12" />
          工具调用
          <span class="text-gray-400 dark:text-gray-500 font-normal">({{ chat.lastToolCalls.length }} 次)</span>
        </div>
        <div v-if="expandedTools" class="space-y-2">
          <div
            v-for="(tc, i) in chat.lastToolCalls"
            :key="i"
            class="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-gray-50 dark:bg-gray-800"
          >
            <div class="flex items-center justify-between mb-1.5">
              <span class="font-mono text-xs font-semibold text-purple-700 dark:text-purple-300">{{ tc.name }}</span>
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-500 dark:text-gray-400">{{ tc.kind }}</span>
            </div>
            <details class="text-xs">
              <summary class="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 select-none">参数/结果</summary>
              <div class="relative group mt-1.5">
                <button
                  @click.stop="copyToClipboard(formatArgs({ arguments: tc.arguments, result: tc.result }), i)"
                  class="absolute right-2 top-2 p-1.5 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 z-10"
                  title="复制"
                >
                  <Check v-if="copiedIndex === i" :size="12" class="text-green-600 dark:text-green-400" />
                  <Copy v-else :size="12" />
                </button>
                <pre class="p-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded overflow-x-auto text-[11px] text-gray-700 dark:text-gray-200 pr-10 max-h-40 overflow-y-auto">{{ formatArgs({ arguments: tc.arguments, result: tc.result }) }}</pre>
              </div>
            </details>
          </div>
        </div>
      </section>

      <!-- ========== RAG 检索结果 ========== -->
      <section v-if="chat.lastRetrievedDocs.length > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
          <BookOpen :size="12" />
          RAG 检索
          <span class="text-gray-400 dark:text-gray-500 font-normal">({{ chat.lastRetrievedDocs.length }} 段)</span>
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
                #{{ i + 1 }} {{ doc.metadata?.file_name || '未知来源' }}
                <span v-if="doc.adopted === false" class="ml-1 text-gray-400 dark:text-gray-500">(未采用)</span>
              </span>
              <div class="flex items-center gap-2">
                <span class="text-[10px]" :class="doc.adopted !== false ? 'text-gray-500 dark:text-gray-400' : 'text-gray-400 dark:text-gray-500'">{{ doc.score?.toFixed(4) }}</span>
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

      <!-- ========== 执行链路 ========== -->
      <section v-if="chat.lastTrace.length > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
          <Clock :size="12" />
          执行链路
        </div>
        <div class="space-y-1">
          <div
            v-for="(step, i) in chat.lastTrace"
            :key="i"
            class="flex items-center gap-2 text-xs py-1 px-2 rounded hover:bg-gray-50 dark:hover:bg-gray-800/50"
          >
            <span class="w-1.5 h-1.5 rounded-full flex-shrink-0"
              :class="{
                'bg-primary-500': step.node === 'supervisor',
                'bg-blue-500': step.node === 'rag_agent',
                'bg-purple-500': step.node === 'tool_agent',
                'bg-gray-400': step.node === 'context_prep',
              }"
            ></span>
            <span class="font-mono font-medium text-gray-700 dark:text-gray-200 min-w-0 truncate">{{ step.node }}</span>
            <span v-if="step.output?.tokens" class="text-amber-600 dark:text-amber-400 whitespace-nowrap">{{ formatTokens(step.output.tokens) }}</span>
            <span class="text-gray-400 dark:text-gray-500 ml-auto whitespace-nowrap">{{ step.elapsed_ms }}ms</span>
          </div>
        </div>
      </section>

      <!-- ========== Token 用量 ========== -->
      <section v-if="totalTokens > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
          <Zap :size="12" class="text-amber-500" />
          Token 用量
        </div>
        <div class="rounded-lg border border-gray-200 dark:border-gray-700 p-3 bg-amber-50/30 dark:bg-amber-900/10">
          <div class="flex flex-wrap gap-x-3 gap-y-1 text-xs mb-2">
            <span v-for="item in nodeTokens" :key="item.node" class="text-gray-600 dark:text-gray-300">
              <span class="font-mono">{{ item.node }}</span>:
              <span class="text-amber-700 dark:text-amber-300 font-semibold">{{ formatTokens(item.tokens) }}</span>
            </span>
          </div>
          <div class="flex items-center justify-between text-xs pt-2 border-t border-gray-200 dark:border-gray-700">
            <span class="text-gray-500 dark:text-gray-400">本次</span>
            <span class="font-semibold text-amber-700 dark:text-amber-300">{{ formatTokens(totalTokens) }} tokens</span>
          </div>
          <div v-if="sessionTotalTokens > 0" class="flex items-center justify-between text-xs mt-1">
            <span class="text-gray-500 dark:text-gray-400">累计</span>
            <span class="font-medium text-gray-600 dark:text-gray-300">{{ formatTokens(sessionTotalTokens) }}</span>
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
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.animate-spin {
  animation: spin 1.2s linear infinite;
}
</style>
