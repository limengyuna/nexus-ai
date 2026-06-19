<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  sending: boolean
}>()

const emit = defineEmits<{
  (e: 'send', text: string): void
  (e: 'stop'): void
}>()

const inputText = ref('')

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    handleSend()
  }
}

function handleSend() {
  const text = inputText.value.trim()
  if (!text) return
  inputText.value = ''
  emit('send', text)
}
</script>

<template>
  <div class="border-t border-gray-100 dark:border-gray-800 p-4 flex-shrink-0 bg-zinc-50 dark:bg-gray-950/20">
    <!-- 文本域与动作按钮 -->
    <div class="flex gap-2.5">
      <textarea
        v-model="inputText"
        placeholder="输入消息，Enter 发送，Shift+Enter 换行"
        rows="2"
        class="flex-1 resize-none px-4 py-2.5 bg-white dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-md text-sm md:text-xs focus:outline-none focus:ring-4 focus:ring-zinc-900/5 focus:border-zinc-400 dark:focus:border-zinc-600 transition-all duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
        :disabled="sending"
        @keydown="onKeyDown"
      ></textarea>
      
      <!-- 双态发送/停止按钮 -->
      <button
        v-if="!sending"
        class="px-5 py-2 bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 text-xs font-bold rounded-md transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed self-end shadow-sm active:scale-95"
        :disabled="!inputText.trim()"
        @click="handleSend"
      >
        发送
      </button>
      <button
        v-else
        class="px-5 py-2 bg-zinc-900 hover:bg-zinc-800 dark:bg-zinc-100 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 text-xs font-bold rounded-md transition-all duration-200 self-end flex items-center gap-1.5 shadow-sm active:scale-95"
        title="停止生成（智能体将在临近步骤完成时退出）"
        @click="$emit('stop')"
      >
        <span class="w-2 h-2 bg-white rounded-xs animate-pulse"></span>
        停止
      </button>
    </div>
  </div>
</template>
