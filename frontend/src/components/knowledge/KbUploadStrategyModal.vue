<script setup lang="ts">
import { ref } from 'vue'
import { FileText } from 'lucide-vue-next'

const props = defineProps<{
  files: File[]
}>()

const emit = defineEmits<{
  (e: 'cancel'): void
  (e: 'confirm', data: { strategy?: 'recursive' | 'markdown' | 'semantic', llmClean?: boolean }): void
}>()

const pendingUploadStrategy = ref<'default' | 'recursive' | 'markdown' | 'semantic'>('default')
const pendingUploadLlmClean = ref<'default' | 'on' | 'off'>('default')

function handleConfirm() {
  const strategyOverride = pendingUploadStrategy.value === 'default' ? undefined : pendingUploadStrategy.value
  const llmCleanOverride = pendingUploadLlmClean.value === 'default'
    ? undefined
    : pendingUploadLlmClean.value === 'on'
    
  emit('confirm', { strategy: strategyOverride, llmClean: llmCleanOverride })
}
</script>

<template>
  <div
    class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 transition-opacity"
    @click.self="$emit('cancel')"
  >
    <div class="bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl border border-zinc-200/60 dark:border-zinc-800 p-8 w-[34rem] flex flex-col max-h-[90vh]">
      <h3 class="text-xl font-bold text-zinc-900 dark:text-zinc-100 mb-2">选择分块策略</h3>
      <p class="text-sm text-zinc-500 dark:text-zinc-400 mb-4">
        将为以下 <span class="font-bold text-zinc-900 dark:text-white">{{ files.length }}</span> 个文件统一应用分块策略。
      </p>

      <div class="flex-1 overflow-y-auto custom-scrollbar pr-2 space-y-6">
        <!-- 文件列表（折叠展示） -->
        <div class="max-h-24 overflow-y-auto bg-zinc-50 dark:bg-zinc-800/40 rounded-xl p-3 space-y-1.5 border border-zinc-100 dark:border-zinc-800/80">
          <div v-for="f in files" :key="f.name" class="truncate text-xs font-mono text-zinc-600 dark:text-zinc-400" :title="f.name">
            <FileText :size="12" class="inline mr-1" /> {{ f.name }}
          </div>
        </div>

        <!-- 分块策略 Card Radios -->
        <div class="space-y-3">
          <div class="text-sm font-semibold text-zinc-800 dark:text-zinc-200">文档切分策略</div>
          <div class="grid grid-cols-1 gap-3">
            <label
              v-for="opt in [
                { value: 'default', title: '沿用知识库默认', desc: '使用当前知识库创建时设置的分块策略' },
                { value: 'recursive', title: 'Recursive (通用)', desc: '递归字符切分，适用于任何纯文本/混合文档' },
                { value: 'markdown', title: 'Markdown (结构化)', desc: '按 # 标题层级切分，完美保留语义树结构（推荐）' },
                { value: 'semantic', title: 'Semantic (语义)', desc: '基于 Embedding 语义跳变切分，适合无明确标题的长文本（较慢）' },
              ]"
              :key="opt.value"
              class="relative flex cursor-pointer rounded-xl border p-4 shadow-sm focus:outline-none transition-all duration-200"
              :class="pendingUploadStrategy === opt.value ? 'bg-zinc-50 dark:bg-zinc-800 border-zinc-900 dark:border-zinc-100 ring-1 ring-zinc-900 dark:ring-zinc-100' : 'border-zinc-200/80 dark:border-zinc-700/80 bg-white dark:bg-zinc-900 hover:bg-zinc-50 dark:hover:bg-zinc-800/80 hover:border-zinc-300 dark:hover:border-zinc-600'"
            >
              <input type="radio" v-model="pendingUploadStrategy" :value="opt.value" class="sr-only" />
              <div class="flex w-full items-center justify-between">
                <div class="flex items-center">
                  <div class="text-sm">
                    <p class="font-medium text-zinc-900 dark:text-zinc-100" :class="pendingUploadStrategy === opt.value ? 'font-bold' : ''">
                      {{ opt.title }}
                    </p>
                    <div class="text-zinc-500 dark:text-zinc-400 text-xs mt-1" :class="pendingUploadStrategy === opt.value ? 'text-zinc-700 dark:text-zinc-300' : ''">
                      <p class="sm:inline">{{ opt.desc }}</p>
                    </div>
                  </div>
                </div>
                <div v-show="pendingUploadStrategy === opt.value" class="shrink-0 text-zinc-900 dark:text-zinc-100">
                  <svg class="h-6 w-6" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="12" fill="currentColor" fill-opacity="0.1" />
                    <path d="M7 13l3 3 7-7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
                  </svg>
                </div>
              </div>
            </label>
          </div>
        </div>

        <!-- LLM 清洗（三态 Card） -->
        <div class="space-y-3">
          <div class="text-sm font-semibold text-zinc-800 dark:text-zinc-200">附加处理项</div>
          <div class="grid grid-cols-3 gap-2">
            <label
              v-for="opt in [
                { value: 'default', label: '沿用 KB 默认' },
                { value: 'on', label: '开启 LLM 清洗' },
                { value: 'off', label: '关闭清洗' },
              ]"
              :key="opt.value"
              class="relative flex cursor-pointer items-center justify-center rounded-lg border py-2.5 px-3 text-xs font-medium uppercase transition-all duration-200 sm:flex-1"
              :class="pendingUploadLlmClean === opt.value ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 border-transparent shadow-sm' : 'bg-white dark:bg-zinc-800 border-zinc-200 dark:border-zinc-700 text-zinc-900 dark:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-700'"
            >
              <input type="radio" v-model="pendingUploadLlmClean" :value="opt.value" class="sr-only" />
              <span>{{ opt.label }}</span>
            </label>
          </div>
        </div>
      </div>

      <div class="mt-6 flex items-center justify-end gap-3 pt-4 border-t border-zinc-100 dark:border-zinc-800/60">
        <button class="px-5 py-2.5 text-sm font-medium text-zinc-600 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors" @click="$emit('cancel')">取消上传</button>
        <button
          class="px-6 py-2.5 text-sm font-medium bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded-lg hover:bg-black dark:hover:bg-white shadow-sm transition-colors"
          @click="handleConfirm"
        >
          确认并开始上传
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 8px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.45);
  border-radius: 9999px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.75);
}
</style>
