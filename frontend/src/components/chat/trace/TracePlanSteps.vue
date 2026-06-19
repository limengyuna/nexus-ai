<script setup lang="ts">
import { computed, ref } from 'vue'
import { Sparkles, BookOpen, Wrench, ChevronDown, ChevronRight, Copy, Check, CircleCheck, Circle, Loader, Building } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()

const taskPlan = computed(() => chat.lastTaskPlan || [])

// 复制功能
const copiedIndex = ref<number | null>(null)
function copyToClipboard(text: string, index: number) {
  navigator.clipboard.writeText(text).then(() => {
    copiedIndex.value = index
    setTimeout(() => { copiedIndex.value = null }, 2000)
  }).catch((err) => console.error('Failed to copy:', err))
}

// 折叠状态
const expandedStepTools = ref<Set<number>>(new Set())
function toggleStepTools(stepNum: number) {
  expandedStepTools.value.has(stepNum) ? expandedStepTools.value.delete(stepNum) : expandedStepTools.value.add(stepNum)
}

const expandedStepDocs = ref<Set<number>>(new Set())
function toggleStepDocs(stepNum: number) {
  expandedStepDocs.value.has(stepNum) ? expandedStepDocs.value.delete(stepNum) : expandedStepDocs.value.add(stepNum)
}

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

// 回溯数据
const parentMergedCount = computed(() => {
  const ragStep = chat.lastTrace.find((s: any) => s.node === 'rag_agent')
  return ragStep?.output?.parent_merged ?? 0
})

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
  if (agent === 'rag_agent') return BookOpen
  if (agent === 'business_context_agent') return Building
  return Wrench
}

function agentLabel(agent: string) {
  if (agent === 'rag_agent') return 'RAG Agent'
  if (agent === 'business_context_agent') return 'Context Agent'
  return 'Tool Agent'
}

function agentBadgeClass(agent: string) {
  if (agent === 'rag_agent') return 'bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100 font-bold'
  if (agent === 'business_context_agent') return 'bg-zinc-100 text-zinc-800 dark:bg-zinc-800 dark:text-zinc-200 font-bold'
  return 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 font-bold'
}
</script>

<template>
  <section v-if="taskPlan.length > 0">
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

          <!-- 步骤卡片（褪色化） -->
          <div
            class="rounded-lg border p-3 transition-all duration-300 shadow-sm"
            :class="{
              'border-zinc-300 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800/50': step.status === 'completed',
              'border-zinc-900 bg-white dark:border-zinc-100 dark:bg-zinc-900 ring-1 ring-zinc-900 dark:ring-zinc-100 animate-border-pulse': step.status === 'in_progress',
              'border-dashed border-gray-200 bg-gray-50/30 dark:border-gray-800 dark:bg-gray-800/10 opacity-70': step.status === 'pending',
            }"
          >
            <div class="flex items-center gap-2 mb-1.5">
              <span class="text-[10px] font-mono font-bold text-gray-400 dark:text-gray-500">STEP {{ step.step }}</span>
              <span class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium" :class="agentBadgeClass(step.agent)">
                <component :is="agentIcon(step.agent)" :size="10" />
                {{ agentLabel(step.agent) }}
              </span>
              <span v-if="step.status === 'completed'" class="ml-auto text-[10px] text-zinc-900 dark:text-zinc-100 font-semibold flex items-center gap-0.5">
                ✓ 完成
              </span>
              <span v-else-if="step.status === 'in_progress'" class="ml-auto text-[10px] text-zinc-900 dark:text-white font-semibold animate-pulse flex items-center gap-1">
                <span class="w-1.5 h-1.5 rounded-full bg-zinc-900 dark:bg-white animate-ping"></span>
                执行中...
              </span>
            </div>
            <p class="text-xs text-gray-700 dark:text-gray-200 leading-relaxed font-medium">
              {{ step.instruction }}
            </p>

            <!-- 步骤内嵌：工具调用明细 -->
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

            <!-- 步骤内嵌：RAG 检索明细 -->
            <div v-if="step.agent === 'rag_agent' && chat.lastRetrievedDocs.length > 0" class="mt-2.5 pt-2 border-t border-gray-100 dark:border-gray-800/50">
              <div 
                class="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                @click.stop="toggleStepDocs(step.step)"
              >
                <component :is="expandedStepDocs.has(step.step) ? ChevronDown : ChevronRight" :size="11" />
                <BookOpen :size="11" class="text-blue-500" />
                <span>此步骤检索知识 ({{ chat.lastRetrievedDocs.length }} 段)</span>
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
</template>

<style scoped>
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.animate-spin { animation: spin 1.2s linear infinite; }

/* 黑白灰高对比度流光呼吸动画 */
@keyframes border-pulse {
  0%, 100% {
    border-color: rgba(0, 0, 0, 0.4);
    box-shadow: 0 0 8px rgba(0, 0, 0, 0.05);
  }
  50% {
    border-color: rgba(0, 0, 0, 0.9);
    box-shadow: 0 0 16px rgba(0, 0, 0, 0.15);
  }
}
@media (prefers-color-scheme: dark) {
  @keyframes border-pulse {
    0%, 100% {
      border-color: rgba(255, 255, 255, 0.4);
      box-shadow: 0 0 8px rgba(255, 255, 255, 0.05);
    }
    50% {
      border-color: rgba(255, 255, 255, 0.9);
      box-shadow: 0 0 16px rgba(255, 255, 255, 0.15);
    }
  }
}
.animate-border-pulse {
  animation: border-pulse 2.2s infinite ease-in-out;
}

@keyframes slide-down {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-slide-down {
  animation: slide-down 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
