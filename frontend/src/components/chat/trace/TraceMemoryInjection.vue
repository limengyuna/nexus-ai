<script setup lang="ts">
import { computed, ref } from 'vue'
import { BookOpen, Wrench, ChevronDown, ChevronRight, Copy, Check, Building, ShieldCheck, CircleCheck, Circle } from 'lucide-vue-next'
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

function formatArgs(args: any): string {
  try { return JSON.stringify(args, null, 2) }
  catch { return String(args) }
}

// 展开状态
const expandedTools = ref(false)
const expandedDocs = ref<Set<number>>(new Set())
const expandedGlobalDocs = ref(false)
const expandedBusinessContext = ref(false)
const expandedFaithClaims = ref(false)

function toggleDoc(index: number) {
  expandedDocs.value.has(index) ? expandedDocs.value.delete(index) : expandedDocs.value.add(index)
}

// 业务上下文
const businessContext = computed(() => chat.lastRetrievedBusinessContext || [])

// 忠实性校验
const faithfulness = computed(() => chat.lastFaithfulness)
const hasFaithfulness = computed(() => {
  const f = faithfulness.value
  return f && typeof f.score === 'number' && f.score >= 0
})
const faithScorePercent = computed(() => {
  const f = faithfulness.value
  if (!f || f.score < 0) return 0
  return Math.round(f.score * 100)
})
const faithScoreColor = computed(() => {
  const p = faithScorePercent.value
  if (p >= 80) return 'text-emerald-600 dark:text-emerald-400'
  if (p >= 50) return 'text-amber-600 dark:text-amber-400'
  return 'text-red-600 dark:text-red-400'
})
const faithBgColor = computed(() => {
  const p = faithScorePercent.value
  if (p >= 80) return 'bg-emerald-50 dark:bg-emerald-900/20 border-emerald-200 dark:border-emerald-800'
  if (p >= 50) return 'bg-amber-50 dark:bg-amber-900/20 border-amber-200 dark:border-amber-800'
  return 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
})

// 回溯数据
const parentMergedCount = computed(() => {
  const ragStep = chat.lastTrace.find((s: any) => s.node === 'rag_agent')
  return ragStep?.output?.parent_merged ?? 0
})
const effectiveHitsCount = computed(() => {
  const ragStep = chat.lastTrace.find((s: any) => s.node === 'rag_agent')
  return ragStep?.output?.effective_hits ?? chat.lastRetrievedDocs.length
})
</script>

<template>
  <div class="space-y-6">
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
      <div v-if="expandedTools" class="space-y-2 animate-slide-down">
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
      <div
        class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5 cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
        @click="expandedGlobalDocs = !expandedGlobalDocs"
      >
        <component :is="expandedGlobalDocs ? ChevronDown : ChevronRight" :size="12" />
        <BookOpen :size="12" />
        全局知识检索
        <span class="text-gray-400 dark:text-gray-500 font-normal">({{ chat.lastRetrievedDocs.length }} 段)</span>
        <span v-if="parentMergedCount > 0" class="px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 text-[9px] font-medium">
          父块回溯合并 → 实际 {{ effectiveHitsCount }} 段送入 LLM
        </span>
      </div>
      <div v-if="expandedGlobalDocs" class="space-y-2 animate-slide-down">
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

    <!-- ========== 业务上下文 ========== -->
    <section v-if="businessContext.length > 0">
      <div
        class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5 cursor-pointer select-none hover:text-gray-700 dark:hover:text-gray-200"
        @click="expandedBusinessContext = !expandedBusinessContext"
      >
        <component :is="expandedBusinessContext ? ChevronDown : ChevronRight" :size="12" />
        <Building :size="12" class="text-orange-500" />
        系统业务上下文
        <span class="text-gray-400 dark:text-gray-500 font-normal">({{ businessContext.length }} 项)</span>
      </div>
      <div v-if="expandedBusinessContext" class="space-y-2 animate-slide-down">
        <div
          v-for="(bc, i) in businessContext"
          :key="i"
          class="border border-gray-200 dark:border-gray-700 rounded-lg p-3 bg-orange-50/30 dark:bg-orange-900/10"
        >
          <div class="flex items-center justify-between mb-1.5">
            <span class="font-mono text-xs font-semibold text-orange-700 dark:text-orange-300">{{ bc.name }}</span>
            <span class="text-[10px] text-gray-400 dark:text-gray-500">{{ bc.elapsed_ms }}ms</span>
          </div>
          <details class="text-xs">
            <summary class="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 select-none">上下文内容</summary>
            <div class="relative group mt-1.5">
              <button
                @click.stop="copyToClipboard(formatArgs({ arguments: bc.arguments, result: bc.result }), i + 200)"
                class="absolute right-2 top-2 p-1.5 rounded bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-sm opacity-0 group-hover:opacity-100 transition-opacity text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200 z-10"
                title="复制"
              >
                <Check v-if="copiedIndex === i + 200" :size="12" class="text-green-600 dark:text-green-400" />
                <Copy v-else :size="12" />
              </button>
              <pre class="p-2 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded overflow-x-auto text-[11px] text-gray-700 dark:text-gray-200 pr-10 max-h-40 overflow-y-auto font-mono">{{ formatArgs({ arguments: bc.arguments, result: bc.result }) }}</pre>
            </div>
          </details>
        </div>
      </div>
    </section>

    <!-- ========== 忠实性校验 ========== -->
    <section v-if="hasFaithfulness">
      <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1.5">
        <ShieldCheck :size="12" class="text-emerald-500" />
        忠实性校验
        <span class="text-gray-400 dark:text-gray-500 font-normal">({{ faithfulness?.elapsed_ms }}ms)</span>
      </div>
      <div class="rounded-xl border p-4" :class="faithBgColor">
        <!-- 评分概览 -->
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <span class="text-2xl font-bold" :class="faithScoreColor">{{ faithScorePercent }}%</span>
            <span class="text-xs text-gray-500 dark:text-gray-400">来源可信度</span>
          </div>
          <div class="text-right text-[10px] text-gray-500 dark:text-gray-400">
            <span :class="faithScoreColor" class="font-semibold">{{ faithfulness?.supported_claims }}</span>
            <span> / {{ faithfulness?.total_claims }} 条声明有据可查</span>
          </div>
        </div>

        <!-- 进度条 -->
        <div class="w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden mb-3">
          <div
            class="h-full rounded-full transition-all duration-500"
            :class="{
              'bg-emerald-500': faithScorePercent >= 80,
              'bg-amber-500': faithScorePercent >= 50 && faithScorePercent < 80,
              'bg-red-500': faithScorePercent < 50,
            }"
            :style="{ width: `${faithScorePercent}%` }"
          ></div>
        </div>

        <!-- 声明列表折叠 -->
        <div
          class="flex items-center gap-1.5 text-[11px] font-semibold text-gray-500 dark:text-gray-400 cursor-pointer select-none hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
          @click="expandedFaithClaims = !expandedFaithClaims"
        >
          <component :is="expandedFaithClaims ? ChevronDown : ChevronRight" :size="11" />
          <span>查看逐条校验明细</span>
        </div>

        <div v-if="expandedFaithClaims" class="mt-2.5 space-y-1.5 animate-slide-down">
          <div
            v-for="(claim, idx) in faithfulness?.claims || []"
            :key="idx"
            class="rounded-lg border p-2.5 text-xs transition-all"
            :class="claim.supported
              ? 'bg-white dark:bg-gray-900 border-emerald-200 dark:border-emerald-800/50'
              : 'bg-white dark:bg-gray-900 border-red-200 dark:border-red-800/50'"
          >
            <div class="flex items-start gap-2">
              <span class="mt-0.5 flex-shrink-0">
                <CircleCheck v-if="claim.supported" :size="14" class="text-emerald-500" />
                <Circle v-else :size="14" class="text-red-400" />
              </span>
              <div class="min-w-0 flex-1">
                <p class="text-gray-700 dark:text-gray-200 leading-relaxed">{{ claim.text }}</p>
                <div class="flex items-center gap-2 mt-1">
                  <span v-if="claim.supported && claim.source_index > 0" class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 font-medium">
                    来源: 资料 #{{ claim.source_index }}
                  </span>
                  <span v-if="!claim.supported" class="text-[10px] px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 font-medium">
                    ⚠️ 未找到来源支撑
                  </span>
                  <span v-if="claim.reason" class="text-[10px] text-gray-400 dark:text-gray-500 truncate">— {{ claim.reason }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
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

@keyframes slide-down {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}
.animate-slide-down {
  animation: slide-down 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}
</style>
