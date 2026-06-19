<script setup lang="ts">
import { ref } from 'vue'

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'create', data: { name: string; description: string; chunk_strategy: string; enable_llm_clean: boolean }): void
}>()

const createForm = ref({
  name: '',
  description: '',
  chunk_strategy: 'recursive' as 'recursive' | 'markdown' | 'semantic',
  enable_llm_clean: false,
})

function handleCreate() {
  emit('create', { ...createForm.value })
}
</script>

<template>
  <div
    class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 transition-opacity"
    @click.self="$emit('close')"
  >
    <div class="bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl border border-zinc-200/60 dark:border-zinc-800 p-7 w-[28rem] space-y-4">
      <h3 class="text-xl font-bold text-zinc-900 dark:text-zinc-100 mb-2">新建知识库</h3>

      <div>
        <label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">名称 *</label>
        <input
          v-model="createForm.name"
          type="text"
          class="w-full px-3.5 py-2.5 border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/50 dark:focus:ring-zinc-100/30 focus:border-zinc-900 dark:focus:border-zinc-100 transition-all"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">描述</label>
        <textarea
          v-model="createForm.description"
          rows="2"
          class="w-full px-3.5 py-2.5 border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/50 dark:focus:ring-zinc-100/30 focus:border-zinc-900 dark:focus:border-zinc-100 transition-all"
        ></textarea>
      </div>

      <div>
        <label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">分块策略</label>
        <select
          v-model="createForm.chunk_strategy"
          class="w-full px-3.5 py-2.5 border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/50 dark:focus:ring-zinc-100/30 focus:border-zinc-900 dark:focus:border-zinc-100 transition-all"
        >
          <option value="recursive">recursive（通用递归字符切分）</option>
          <option value="markdown">markdown（按标题层级切分，保留语义结构）</option>
          <option value="semantic">semantic（基于 Embedding 语义跳变切分，适合无明确结构的长文本，较慢）</option>
        </select>
      </div>

      <!-- LLM 文档清洗开关 -->
      <div class="flex items-start gap-3 p-3.5 bg-zinc-50 dark:bg-zinc-800/40 border border-zinc-200 dark:border-zinc-700/80 rounded-xl">
        <input
          id="enable-llm-clean"
          v-model="createForm.enable_llm_clean"
          type="checkbox"
          class="mt-1 h-4 w-4 rounded border-zinc-300 text-zinc-900 dark:text-zinc-100 focus:ring-zinc-900"
        />
        <label for="enable-llm-clean" class="flex-1 text-sm text-zinc-700 dark:text-zinc-300 cursor-pointer">
          <span class="font-semibold block mb-0.5 text-zinc-900 dark:text-zinc-100">启用 LLM 文档清洗（实验性）</span>
          <span class="text-xs text-zinc-500 dark:text-zinc-400 leading-relaxed">
            上传时额外调用 LLM 将格式混乱的 PDF 重排为标准 Markdown，提升分块质量。
            含 5 道防线防止内容被篡改。仅对本知识库生效，会增加 token 消耗和上传处理时间。
          </span>
        </label>
      </div>

      <div class="flex justify-end gap-3 pt-4 border-t border-zinc-100 dark:border-zinc-800/60 mt-2">
        <button class="px-5 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors" @click="$emit('close')">取消</button>
        <button
          class="px-5 py-2 text-sm font-medium bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded-lg hover:bg-black dark:hover:bg-white shadow-sm transition-colors"
          @click="handleCreate"
        >
          创建
        </button>
      </div>
    </div>
  </div>
</template>
