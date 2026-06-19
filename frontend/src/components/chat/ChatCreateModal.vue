<script setup lang="ts">
import { ref } from 'vue'
import type { KnowledgeBase } from '@/api/knowledge'

defineProps<{
  knowledgeBases: KnowledgeBase[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'create', title: string, kbId: number | null): void
}>()

const title = ref('')
const kbId = ref<number | null>(null)

function handleCreate() {
  emit('create', title.value.trim() || '新对话', kbId.value)
}
</script>

<template>
  <div
    class="fixed inset-0 bg-black/40 dark:bg-black/60 flex items-center justify-center z-50 px-4 transition-opacity"
    @click.self="$emit('close')"
  >
    <div class="bg-white/95 dark:bg-zinc-950 rounded-md border border-white/20 dark:border-white/5 shadow-lg border border-zinc-200 dark:border-zinc-800 p-6 w-full max-w-sm space-y-4">
      <h3 class="text-sm font-extrabold text-gray-800 dark:text-gray-100 font-outfit tracking-wide uppercase">新建智能对话会话</h3>

      <div>
        <label class="block text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase mb-1.5 ml-0.5">会话标题（可选）</label>
        <input
          v-model="title"
          type="text"
          placeholder="留空则以首条提问为标题"
          class="w-full px-3 py-2 bg-white dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-md text-xs focus:outline-none focus:ring-4 focus:ring-zinc-900/5 focus:border-zinc-400 dark:border-zinc-600 transition-all placeholder:text-gray-400 dark:placeholder:text-gray-500"
          @keydown.enter="handleCreate"
        />
      </div>

      <div>
        <label class="block text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase mb-1.5 ml-0.5">关联知识库库管道（可选，启用 RAG）</label>
        <select
          v-model="kbId"
          class="w-full px-3 py-2 bg-white dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-md text-xs focus:outline-none focus:ring-4 focus:ring-zinc-900/5 focus:border-zinc-400 dark:border-zinc-600 transition-all"
        >
          <option :value="null">（不关联，仅通用闲聊或协作）</option>
          <option v-for="k in knowledgeBases" :key="k.id" :value="k.id">
            {{ k.name }}（{{ k.document_count }} 篇文档数据）
          </option>
        </select>
      </div>

      <div class="flex justify-end gap-2.5 pt-2">
        <button class="px-3.5 py-1.5 text-xs font-bold text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors" @click="$emit('close')">
          取消
        </button>
        <button
          class="px-5 py-1.5 text-xs font-bold bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 rounded-[10px] hover:bg-zinc-800 dark:hover:bg-zinc-200 shadow-sm transition-colors active:scale-95"
          @click="handleCreate"
        >
          创建会话
        </button>
      </div>
    </div>
  </div>
</template>
