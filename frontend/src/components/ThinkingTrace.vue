<script setup lang="ts">
/**
 * 思考过程面板 — Task Pipeline 视图
 *
 * 展示 Supervisor 的任务拆解和分步执行进度：
 * 1. 顶部：Supervisor 决策摘要（intent + 计划概述 + 渐变发光进度条）
 * 2. 核心：Task Plan 进度管道（内嵌关联工具及知识库的折叠卡片 + 紫绿流光呼吸动效）
 * 3. 详情：全局工具调用 / RAG 检索明细折叠
 * 4. 底部：执行链路时间线 + Token 用量
 */
import { computed, ref } from 'vue'
import {
  Sparkles, Zap, Copy, Check, CircleCheck, Circle, Loader,
  BookOpen, Wrench, ChevronDown, ChevronRight, Clock, Brain
} from 'lucide-vue-next'

import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

// 复制功能
const copiedIndex = ref<number | null>(null)
function copyToClipboard(text: string, index: number) {
  navigator.clipboard.writeText(text).then(() => {
    copiedIndex.value = index
    setTimeout(() => { copiedIndex.value = null }, 2000)
  }).catch((err) => console.error('Failed to copy:', err))
}

// 步骤卡片内部的工具折叠状态
const expandedStepTools = ref<Set<number>>(new Set())
function toggleStepTools(stepNum: number) {
  if (expandedStepTools.value.has(stepNum)) {
    expandedStepTools.value.delete(stepNum)
  } else {
    expandedStepTools.value.add(stepNum)
  }
}

// 步骤卡片内部的文档折叠状态
const expandedStepDocs = ref<Set<number>>(new Set())
function toggleStepDocs(stepNum: number) {
  if (expandedStepDocs.value.has(stepNum)) {
    expandedStepDocs.value.delete(stepNum)
  } else {
    expandedStepDocs.value.add(stepNum)
  }
}

// RAG 全局片段展开
const expandedDocs = ref<Set<number>>(new Set())
function toggleDoc(index: number) {
  expandedDocs.value.has(index) ? expandedDocs.value.delete(index) : expandedDocs.value.add(index)
}

// 全局工具调用展开
const expandedTools = ref(false)

// 决策历史展开状态
const expandedDecisions = ref(false)

// 决策历史：倒序展示（最新一条放最上面），且过滤掉当前最新的（在卡片上方已展示）
const previousDecisions = computed(() => {
  const list = chat.lastDecisions || []
  if (list.length <= 1) return []
  // 最新一条是数组末尾，前面的都是历史，按时间倒序返回（最近的在前）
  return list.slice(0, -1).reverse()
})

function decisionIntentClass(intent: string) {
  if (intent === 'rag') return 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
  if (intent === 'tool') return 'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300'
  return 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-300'
}

const hasData = computed(() =>
  chat.lastIntent || chat.lastTrace.length > 0 || chat.lastToolCalls.length > 0 || chat.lastTaskPlan.length > 0,
)

// Task Plan
const taskPlan = computed(() => chat.lastTaskPlan || [])
const hasTaskPlan = computed(() => taskPlan.value.length > 0)
const completedSteps = computed(() => taskPlan.value.filter((s: any) => s.status === 'completed').length)
const totalSteps = computed(() => taskPlan.value.length)

// 按步骤分组的工具调用
const toolCallsByStep = computed(() => {
  const map: Record<number, any[]> = {}
  for (const tc of chat.lastToolCalls) {
    const step = tc.step ?? 0
    if (!map[step]) map[step] = []
    map[step].push(tc)
  }
  return map
})

// Parent-Child 回溯统计（从 rag_agent 的 output_summary 中提取）
const parentMergedCount = computed(() => {
  const ragStep = chat.lastTrace.find((s: any) => s.node === 'rag_agent')
  return ragStep?.output?.parent_merged ?? 0
})
const effectiveHitsCount = computed(() => {
  const ragStep = chat.lastTrace.find((s: any) => s.node === 'rag_agent')
  return ragStep?.output?.effective_hits ?? chat.lastRetrievedDocs.length
})

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
  if (status === 'completed') return 'text-emerald-500 dark:text-emerald-400'
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

        <!-- 渐变发光计划概览 -->
        <div v-if="hasTaskPlan" class="mt-3 flex items-center gap-2">
          <div class="flex-1 h-2 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden border border-gray-100/10 dark:border-gray-800/10">
            <div
              class="h-full bg-gradient-to-r from-violet-500 via-teal-400 to-emerald-400 rounded-full transition-all duration-700 ease-out shadow-[0_0_8px_rgba(16,185,129,0.4)]"
              :style="{ width: totalSteps > 0 ? `${(completedSteps / totalSteps) * 100}%` : '0%' }"
            ></div>
          </div>
          <span class="text-[10px] font-mono text-gray-500 dark:text-gray-400 whitespace-nowrap bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded">
            {{ completedSteps }}/{{ totalSteps }}
          </span>
        </div>
      </section>

      <!-- ========== Task Plan 管道 ========== -->
      <section v-if="hasTaskPlan">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-3 flex items-center gap-1.5">
          <Sparkles :size="12" class="text-primary-500" />
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
              <div class="absolute left-0 top-0.5 w-[30px] flex justify-center z-10">
                <div class="bg-white dark:bg-gray-900 rounded-full p-0.5">
                  <component
                    :is="stepStatusIcon(step.status)"
                    :size="16"
                    :stroke-width="2.5"
                    :class="stepStatusColor(step.status)"
                  />
                </div>
              </div>

              <!-- 步骤卡片 -->
              <div
                class="rounded-lg border p-3 transition-all duration-300 shadow-sm"
                :class="{
                  'border-emerald-200 bg-gradient-to-br from-emerald-50/50 to-emerald-50/10 dark:border-emerald-950 dark:bg-emerald-950/20 shadow-emerald-100/50 dark:shadow-none': step.status === 'completed',
                  'border-primary-400 bg-gradient-to-br from-primary-50/50 to-primary-50/10 dark:border-primary-850 dark:bg-primary-950/20 ring-1 ring-primary-300 dark:ring-primary-700 shadow-lg shadow-primary-500/5 dark:shadow-none animate-border-pulse': step.status === 'in_progress',
                  'border-dashed border-gray-200 bg-gray-50/30 dark:border-gray-800 dark:bg-gray-800/10 opacity-70': step.status === 'pending',
                }"
              >
                <div class="flex items-center gap-2 mb-1.5">
                  <span class="text-[10px] font-mono font-bold text-gray-400 dark:text-gray-500">STEP {{ step.step }}</span>
                  <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium" :class="agentBadgeClass(step.agent)">
                    <component :is="agentIcon(step.agent)" :size="10" />
                    {{ agentLabel(step.agent) }}
                  </span>
                  <span v-if="step.status === 'completed'" class="ml-auto text-[10px] text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-0.5">
                    ✓ 完成
                  </span>
                  <span v-else-if="step.status === 'in_progress'" class="ml-auto text-[10px] text-primary-600 dark:text-primary-400 font-semibold animate-pulse flex items-center gap-1">
                    <span class="w-1.5 h-1.5 rounded-full bg-primary-500 animate-ping"></span>
                    执行中...
                  </span>
                </div>
                <p class="text-xs text-gray-700 dark:text-gray-200 leading-relaxed font-medium">
                  {{ step.instruction }}
                </p>

                <!-- 步骤内嵌：工具调用明细（重磅升级） -->
                <div v-if="step.agent === 'tool_agent' && (toolCallsByStep[step.step] || []).length > 0" class="mt-2.5 pt-2 border-t border-gray-100 dark:border-gray-800/50">
                  <div 
                    class="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                    @click.stop="toggleStepTools(step.step)"
                  >
                    <component :is="expandedStepTools.has(step.step) ? ChevronDown : ChevronRight" :size="11" />
                    <Wrench :size="11" class="text-purple-500" />
                    <span>此步骤工具调用 ({{ (toolCallsByStep[step.step] || []).length }} 次)</span>
                  </div>
                  <div v-if="expandedStepTools.has(step.step)" class="mt-2 space-y-1.5 animate-slide-down">
                    <div 
                      v-for="(tc, tcIdx) in toolCallsByStep[step.step] || []" 
                      :key="tcIdx"
                      class="border border-gray-100 dark:border-gray-800/80 rounded-lg p-2.5 bg-white dark:bg-gray-900 shadow-sm"
                    >
                      <div class="flex items-center justify-between text-[11px] mb-1">
                        <span class="font-mono font-semibold text-purple-700 dark:text-purple-300 truncate max-w-[150px]">{{ tc.name }}</span>
                        <span class="text-[9px] px-1.5 py-0.5 rounded bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 font-medium scale-90">{{ tc.kind }}</span>
                      </div>
                      <details class="text-[10px]">
                        <summary class="cursor-pointer text-gray-450 dark:text-gray-400 hover:text-gray-650 dark:hover:text-gray-250 select-none">参数 / 返回值</summary>
                        <div class="relative group mt-1">
                          <button
                            @click.stop="copyToClipboard(formatArgs({ arguments: tc.arguments, result: tc.result }), tcIdx + 100)"
                            class="absolute right-1 top-1 p-1 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-gray-650 dark:text-gray-500 dark:hover:text-gray-300 z-10 shadow-sm"
                            title="复制"
                          >
                            <Check v-if="copiedIndex === tcIdx + 100" :size="10" class="text-green-500" />
                            <Copy v-else :size="10" />
                          </button>
                          <pre class="p-1.5 bg-gray-50 dark:bg-gray-950 border border-gray-100 dark:border-gray-800/80 rounded text-[9px] text-gray-600 dark:text-gray-450 overflow-x-auto max-h-32 overflow-y-auto font-mono pr-8">{{ formatArgs({ arguments: tc.arguments, result: tc.result }) }}</pre>
                        </div>
                      </details>
                    </div>
                  </div>
                </div>

                <!-- 步骤内嵌：RAG 检索明细（重磅升级） -->
                <div v-if="step.agent === 'rag_agent' && chat.lastRetrievedDocs.length > 0" class="mt-2.5 pt-2 border-t border-gray-100 dark:border-gray-800/50">
                  <div 
                    class="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                    @click.stop="toggleStepDocs(step.step)"
                  >
                    <component :is="expandedStepDocs.has(step.step) ? ChevronDown : ChevronRight" :size="11" />
                    <BookOpen :size="11" class="text-blue-500" />
                    <span>此步骤检索知识 ({{ chat.lastRetrievedDocs.length }} 段)</span>
                    <!-- Parent-Child 回溯标记 -->
                    <span v-if="parentMergedCount > 0" class="ml-1 px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 text-[9px] font-medium">
                      父块回溯 -{{ parentMergedCount }}
                    </span>
                  </div>
                  <div v-if="expandedStepDocs.has(step.step)" class="mt-2 space-y-1.5 animate-slide-down">
                    <div 
                      v-for="(doc, docIdx) in chat.lastRetrievedDocs.slice(0, 3)" 
                      :key="docIdx"
                      class="border rounded-lg p-2.5 bg-white dark:bg-gray-900 shadow-sm transition-all"
                      :class="doc.adopted !== false ? 'border-blue-100 dark:border-blue-900/40' : 'border-gray-100 dark:border-gray-800 opacity-60'"
                    >
                      <div class="flex items-center justify-between text-[10px] mb-1">
                        <span class="font-medium text-blue-700 dark:text-blue-400 truncate max-w-[160px]">#{{ docIdx + 1 }} {{ doc.metadata?.file_name || '知识片段' }}</span>
                        <span class="text-[9px] text-gray-400 dark:text-gray-500">{{ doc.score?.toFixed(3) }}</span>
                      </div>
                      <p class="text-[10px] text-gray-500 dark:text-gray-450 line-clamp-2 leading-relaxed whitespace-pre-wrap break-all">{{ doc.content }}</p>
                    </div>
                  </div>
                </div>

              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ========== 全局明细折叠面板：工具调用 ========== -->
      <section v-if="chat.lastToolCalls.length > 0">
        <div
          class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5 cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
          @click="expandedTools = !expandedTools"
        >
          <component :is="expandedTools ? ChevronDown : ChevronRight" :size="12" />
          <Wrench :size="12" />
          全局工具日志
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
                <pre class="p-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded overflow-x-auto text-[11px] text-gray-700 dark:text-gray-200 pr-10 max-h-40 overflow-y-auto font-mono">{{ formatArgs({ arguments: tc.arguments, result: tc.result }) }}</pre>
              </div>
            </details>
          </div>
        </div>
      </section>

      <!-- ========== 全局明细折叠面板：RAG 检索结果 ========== -->
      <section v-if="chat.lastRetrievedDocs.length > 0">
        <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
          <BookOpen :size="12" />
          全局知识检索
          <span class="text-gray-400 dark:text-gray-500 font-normal">({{ chat.lastRetrievedDocs.length }} 段)</span>
          <span v-if="parentMergedCount > 0" class="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 text-[9px] font-medium">
            父块回溯合并 → 实际 {{ effectiveHitsCount }} 段送入 LLM
          </span>
        </div>
        <div class="space-y-2">
          <div
            v-for="(doc, i) in chat.lastRetrievedDocs.slice(0, 5)"
            :key="i"
            class="border rounded-lg p-2.5 cursor-pointer transition-colors"
            :class="doc.adopted !== false
              ? 'border-blue-250 dark:border-blue-800 bg-blue-50/40 dark:bg-blue-900/20 hover:bg-blue-50/70 dark:hover:bg-blue-900/30'
              : 'border-gray-200 dark:border-gray-700 bg-gray-50/40 dark:bg-gray-800/30 opacity-60 hover:opacity-80'"
            @click="toggleDoc(i)"
          >
            <div class="flex items-center justify-between mb-1">
              <span class="text-xs font-medium" :class="doc.adopted !== false ? 'text-blue-700 dark:text-blue-300' : 'text-gray-500 dark:text-gray-400'">
                #{{ i + 1 }} {{ doc.metadata?.file_name || '未知来源' }}
                <span v-if="doc.adopted === false" class="ml-1 text-gray-400 dark:text-gray-500">(未采用)</span>
                <span v-if="doc.metadata?.parent_content" class="ml-1 px-1 py-0.5 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 rounded text-[9px] font-medium">子块</span>
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
            <!-- 子块的 Parent 内容折叠区 -->
            <details v-if="expandedDocs.has(i) && doc.metadata?.parent_content" class="mt-1.5" @click.stop>
              <summary class="text-[10px] text-amber-600 dark:text-amber-400 cursor-pointer hover:underline select-none">
                查看完整父块（{{ doc.metadata.parent_content.length }} 字符）
              </summary>
              <p class="mt-1 text-[10px] text-gray-500 dark:text-gray-400 leading-relaxed whitespace-pre-wrap break-words bg-amber-50/50 dark:bg-amber-900/10 rounded p-2 max-h-40 overflow-y-auto">
                {{ doc.metadata.parent_content }}
              </p>
            </details>
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

/* 高端紫绿流光呼吸动画 */
@keyframes border-pulse {
  0%, 100% {
    border-color: rgba(139, 92, 246, 0.4);
    box-shadow: 0 0 8px rgba(139, 92, 246, 0.08);
  }
  50% {
    border-color: rgba(16, 185, 129, 0.8);
    box-shadow: 0 0 16px rgba(16, 185, 129, 0.2);
  }
}
.animate-border-pulse {
  animation: border-pulse 2.2s infinite ease-in-out;
}

/* 折叠面板展开微动画 */
@keyframes slide-down {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.animate-slide-down {
  animation: slide-down 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
</style>
