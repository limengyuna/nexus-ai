<script setup lang="ts">
import { Play, Loader2, Database, TerminalSquare, ChevronRight } from 'lucide-vue-next'
import type { SkillInfo, SkillTestResult } from '@/api/skill'

const props = defineProps<{
  activeSkill: SkillInfo
  needsKb: boolean
  kbList: { id: number; name: string; document_count: number }[]
  testInput: string
  testKbId: number | null
  testing: boolean
  testResult: SkillTestResult | null
}>()

const emit = defineEmits<{
  (e: 'update:testInput', val: string): void
  (e: 'update:testKbId', val: number | null): void
  (e: 'test'): void
}>()

function onInput(e: Event) {
  emit('update:testInput', (e.target as HTMLInputElement).value)
}

function onKbChange(e: Event) {
  const val = (e.target as HTMLSelectElement).value
  emit('update:testKbId', val ? Number(val) : null)
}
</script>

<template>
  <div class="flex-1 overflow-y-auto px-8 py-6 bg-white dark:bg-zinc-950">
    <div class="text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-4 flex items-center gap-2">
      <Play :size="14" class="text-emerald-500" />
      <span>测试执行 (Playground)</span>
    </div>

    <!-- 控制面板区 -->
    <div class="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 p-4 rounded-2xl shadow-sm space-y-4 mb-6">
      
      <!-- 知识库选择器 -->
      <div v-if="needsKb" class="space-y-1.5">
        <label class="flex items-center gap-1.5 text-xs font-semibold text-zinc-600 dark:text-zinc-300">
          <Database :size="12" />
          <span>关联知识库 <span class="text-red-500">*</span></span>
        </label>
        <select
          :value="testKbId"
          @change="onKbChange"
          class="w-full px-3 py-2.5 text-sm font-medium bg-zinc-50 dark:bg-zinc-950/50 text-zinc-800 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-800 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-shadow appearance-none"
        >
          <option :value="null" disabled>请选择检索目标...</option>
          <option v-for="k in kbList" :key="k.id" :value="k.id">
            {{ k.name }} ({{ k.document_count }} docs)
          </option>
        </select>
      </div>

      <!-- 输入框和执行按钮 -->
      <div class="flex flex-col sm:flex-row gap-3">
        <div class="flex-1 relative">
          <input
            :value="testInput"
            @input="onInput"
            type="text"
            placeholder="输入你的 Prompt / 问题进行技能测试..."
            class="w-full px-4 py-2.5 text-sm bg-zinc-50 dark:bg-zinc-950/50 text-zinc-800 dark:text-zinc-100 border border-zinc-200 dark:border-zinc-800 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500/50 transition-shadow placeholder:text-zinc-400 dark:placeholder:text-zinc-600 font-medium"
            :disabled="testing"
            @keydown.enter="$emit('test')"
          />
        </div>
        <button
          class="px-6 py-2.5 text-sm font-bold bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 rounded-xl hover:bg-zinc-800 dark:hover:bg-white disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 flex-shrink-0 transition-colors shadow-sm"
          :disabled="testing || !testInput.trim()"
          @click="$emit('test')"
        >
          <Loader2 v-if="testing" :size="14" class="animate-spin" />
          <Play v-else :size="14" class="fill-current" />
          <span>{{ testing ? '执行中...' : '开始执行' }}</span>
        </button>
      </div>
    </div>

    <!-- 极客风格终端测试结果 -->
    <div v-if="testResult" class="rounded-2xl overflow-hidden border border-zinc-800 bg-[#0c0c0e] shadow-xl text-zinc-300 font-mono text-sm leading-relaxed mb-8">
      
      <!-- 终端头部 -->
      <div class="px-4 py-2.5 bg-zinc-900 border-b border-zinc-800 flex items-center gap-2">
        <TerminalSquare :size="14" class="text-zinc-500" />
        <span class="text-xs font-bold text-zinc-400 tracking-wider">OUTPUT CONSOLE</span>
      </div>

      <!-- 最终回答 -->
      <div class="p-5">
        <div class="flex items-center gap-2 text-emerald-400 mb-2 font-bold text-xs">
          <ChevronRight :size="12" />
          <span>[RESULT] Final Answer</span>
        </div>
        <div class="pl-5 whitespace-pre-wrap text-[13px] text-zinc-100 font-sans leading-loose">
          {{ testResult.answer }}
        </div>
      </div>

      <!-- Tool 调用记录 -->
      <div v-if="testResult.tool_calls.length > 0" class="border-t border-zinc-800/80">
        <div class="px-5 py-3 bg-zinc-900/30 flex items-center gap-2 text-amber-400/80 font-bold text-xs">
          <ChevronRight :size="12" />
          <span>[TRACE] Tool Invocation Chain ({{ testResult.tool_calls.length }} events)</span>
        </div>
        
        <div class="divide-y divide-zinc-800/50">
          <details
            v-for="(tc, i) in testResult.tool_calls"
            :key="i"
            class="group"
          >
            <summary class="px-5 py-3 cursor-pointer hover:bg-zinc-800/30 flex items-center gap-3 select-none transition-colors">
              <span class="text-zinc-500 text-[10px] opacity-60 group-open:rotate-90 transition-transform">▶</span>
              <span class="font-bold text-purple-400 text-xs">{{ tc.name }}</span>
              <span class="px-1.5 py-0.5 rounded text-[9px] uppercase tracking-widest bg-zinc-800 text-zinc-500">{{ tc.kind ?? 'tool' }}</span>
            </summary>
            <div class="px-5 pb-4 pt-1">
              <div class="bg-black/50 rounded-lg p-4 border border-zinc-800/50">
                <pre class="text-[11px] text-zinc-400 overflow-x-auto whitespace-pre-wrap">{{ JSON.stringify({ arguments: tc.arguments, result: tc.result }, null, 2) }}</pre>
              </div>
            </div>
          </details>
        </div>
      </div>

      <!-- Meta 信息 -->
      <div v-if="testResult.meta && Object.keys(testResult.meta).length" class="border-t border-zinc-800/80">
        <details class="group">
          <summary class="px-5 py-3 cursor-pointer hover:bg-zinc-800/30 flex items-center gap-3 select-none transition-colors">
            <span class="text-zinc-500 text-[10px] opacity-60 group-open:rotate-90 transition-transform">▶</span>
            <span class="font-bold text-zinc-500 text-xs uppercase">[META] Execution Context</span>
          </summary>
          <div class="px-5 pb-4 pt-1">
            <div class="bg-black/50 rounded-lg p-4 border border-zinc-800/50">
              <pre class="text-[11px] text-zinc-500 overflow-x-auto whitespace-pre-wrap">{{ JSON.stringify(testResult.meta, null, 2) }}</pre>
            </div>
          </div>
        </details>
      </div>

    </div>
  </div>
</template>

<style scoped>
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.animate-spin {
  animation: spin 1s linear infinite;
}
</style>
