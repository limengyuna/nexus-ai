<script setup lang="ts">
import { ref } from 'vue'
import { Info } from 'lucide-vue-next'

const props = defineProps<{
  initialName: string
  initialDescription: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'save', data: { name: string; description: string }): void
}>()

const editForm = ref({
  name: props.initialName,
  description: props.initialDescription,
})

function handleSave() {
  emit('save', { ...editForm.value })
}
</script>

<template>
  <div
    class="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 transition-opacity"
    @click.self="$emit('close')"
  >
    <div class="bg-white dark:bg-zinc-900 rounded-2xl shadow-2xl border border-zinc-200/60 dark:border-zinc-800 p-7 w-[28rem] space-y-4">
      <h3 class="text-xl font-bold text-zinc-900 dark:text-zinc-100 mb-2">编辑知识库</h3>

      <div>
        <label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">名称 *</label>
        <input
          v-model="editForm.name"
          type="text"
          class="w-full px-3.5 py-2.5 border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/50 dark:focus:ring-zinc-100/30 focus:border-zinc-900 dark:focus:border-zinc-100 transition-all"
          @keydown.enter="handleSave"
        />
      </div>

      <div>
        <label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-1.5">描述</label>
        <textarea
          v-model="editForm.description"
          rows="3"
          class="w-full px-3.5 py-2.5 border border-zinc-300 dark:border-zinc-700 bg-white dark:bg-zinc-900 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-zinc-900/50 dark:focus:ring-zinc-100/30 focus:border-zinc-900 dark:focus:border-zinc-100 transition-all"
        ></textarea>
      </div>

      <div class="text-xs text-zinc-500 dark:text-zinc-400 bg-zinc-50/80 dark:bg-zinc-800/50 px-3.5 py-3 rounded-xl flex items-start gap-2.5">
        <Info :size="16" :stroke-width="2" class="flex-shrink-0 mt-0.5 text-zinc-500" />
        <span class="leading-relaxed">提示：分块策略创建后不可修改（已上传的文档不会按新策略重新切分）。如确需更换，建议新建一个知识库重新上传。</span>
      </div>

      <div class="flex justify-end gap-3 pt-4 border-t border-zinc-100 dark:border-zinc-800/60 mt-2">
        <button class="px-5 py-2 text-sm font-medium text-zinc-600 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors" @click="$emit('close')">取消</button>
        <button
          class="px-5 py-2 text-sm font-medium bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded-lg hover:bg-black dark:hover:bg-white shadow-sm disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
          :disabled="!editForm.name.trim()"
          @click="handleSave"
        >
          保存修改
        </button>
      </div>
    </div>
  </div>
</template>
