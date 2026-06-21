<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { ArrowDown, MessageSquare, Sparkles } from 'lucide-vue-next'
import type { ChatMessage } from '@/api/chat'
import MessageBubble from '@/components/MessageBubble.vue'
import ImmersiveThinkingPanel from './ImmersiveThinkingPanel.vue'

const props = defineProps<{
  activeSessionId: number | null
  messages: ChatMessage[]
  sending: boolean
}>()

const emit = defineEmits<{
  (e: 'regenerate'): void
  (e: 'stop-generating'): void
}>()

const messagesRef = ref<HTMLDivElement | null>(null)
const showScrollToBottom = ref(false)

function handleScroll() {
  if (!messagesRef.value) return
  const el = messagesRef.value
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  showScrollToBottom.value = distanceFromBottom > 200
}

function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTo({ top: messagesRef.value.scrollHeight, behavior: 'smooth' })
  }
}

watch(
  () => props.messages.length,
  () => nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
)
</script>

<template>
  <div class="flex-1 relative overflow-hidden bg-white dark:bg-zinc-950">
    <div
      ref="messagesRef"
      class="absolute inset-0 overflow-y-auto px-6 py-6 space-y-5"
      @scroll="handleScroll"
    >
      <div v-if="!activeSessionId" class="h-full flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 font-medium text-xs space-y-2">
        <MessageSquare :size="24" class="text-gray-300 dark:text-gray-700 animate-pulse" />
        <span>请选择或创建一个会话开始对话</span>
      </div>
      <template v-else>
        <div v-if="messages.length === 0" class="h-full flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 font-medium text-xs space-y-2 py-12">
          <Sparkles :size="20" class="text-gray-300 dark:text-gray-700" />
          <span>还没有消息，向 NexusAI 智能体提问吧</span>
        </div>
        
        <MessageBubble
          v-for="(m, idx) in messages"
          :key="m.id"
          :message="m"
          :is-last-assistant="m.role === 'assistant' && idx === messages.length - 1 && !sending"
          @regenerate="$emit('regenerate')"
        />
        
        <!-- Agent 正在思考中 (沉浸式思考面板) -->
        <div v-if="sending && !messages.some(m => m.role === 'assistant' && m.id < 0 && m.content)" class="flex justify-start w-full max-w-3xl">
          <ImmersiveThinkingPanel />
        </div>
      </template>
    </div>

    <!-- 滚到底部悬浮按钮 -->
    <transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0 translate-y-2"
      enter-to-class="opacity-100 translate-y-0"
      leave-active-class="transition-all duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0"
      leave-to-class="opacity-0 translate-y-2"
    >
      <button
        v-if="showScrollToBottom"
        class="absolute bottom-4 left-1/2 -translate-x-1/2 w-9 h-9 rounded-full bg-white/90 dark:bg-gray-800/90 border border-gray-200/60 dark:border-gray-700/60 shadow-lg flex items-center justify-center text-gray-500 dark:text-gray-300 hover:text-zinc-900 dark:text-zinc-100 dark:hover:text-primary-400 hover:bg-zinc-100/50 dark:hover:bg-primary-950/40 transition-all active:scale-90 z-10"
        title="滚到最新消息"
        @click="scrollToBottom"
      >
        <ArrowDown :size="16" :stroke-width="2.5" />
      </button>
    </transition>
  </div>
</template>
