<script setup lang="ts">
/**
 * 消息气泡组件
 *
 * - 用户消息：右侧 + 主色背景
 * - AI 消息：左侧 + 白底 + Markdown 渲染 + hover 显示复制/重新生成
 */
import { computed, ref } from 'vue'
import { Check, Copy, RotateCcw, ShieldCheck, Sparkles } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import type { ChatMessage } from '@/api/chat'
import { renderMarkdown } from '@/utils/markdown'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  message: ChatMessage
  isLastAssistant?: boolean  // 是否当前会话的最后一条 AI 消息（用于显示"重新生成"按钮）
}>()

const emit = defineEmits<{
  regenerate: []
}>()

const chatStore = useChatStore()

const isUser = computed(() => props.message.role === 'user')
const renderedHtml = computed(() => renderMarkdown(props.message.content))

// 判断 LocalStorage 中是否有该条消息的思考快照
const hasStoredTrace = computed(() => {
  if (isUser.value) return false
  try {
    const raw = localStorage.getItem('nexus_thinking_traces')
    if (!raw) return false
    const tracesStore = JSON.parse(raw)
    const conv = tracesStore.find((item: any) => item.sessionId === props.message.session_id)
    if (conv && conv.snapshots) {
      return conv.snapshots.some((s: any) => s.messageId === props.message.id)
    }
  } catch {}
  return false
})

// 判断当前右侧展示的是否是本消息的思考过程
const isThinkingActive = computed(() => {
  return chatStore.activeThinkingMessageId === props.message.id
})

function viewTraceOfThisMessage() {
  chatStore.loadThinkingTraceForMessage(props.message.session_id, props.message.id)
  toast.success('已载入该条消息的推理链路')
}

// 复制成功瞬时反馈（图标短暂切换为 ✓）
const copied = ref(false)

async function copyContent() {
  try {
    await navigator.clipboard.writeText(props.message.content)
    copied.value = true
    toast.success('已复制到剪贴板')
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    toast.error('复制失败：浏览器拒绝了剪贴板访问')
  }
}

// Agent 来源标签
const sourceLabel = computed(() => {
  const src = props.message.agent_source
  if (!src || src === 'user') return ''
  const map: Record<string, string> = {
    router: 'Router',
    rag: 'RAG Agent',
    tool: 'Tool Agent',
    summary: '摘要',
  }
  return map[src] || src
})

// 格式化消息时间为可读字符串
const timeLabel = computed(() => {
  if (!props.message.created_at) return ''
  const d = new Date(props.message.created_at)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
})

// 简短时间（仅 HH:mm）显示在气泡下方
const shortTime = computed(() => {
  if (!props.message.created_at) return ''
  const d = new Date(props.message.created_at)
  return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
})
</script>

<template>
  <div v-if="isUser || message.content" class="group flex" :class="isUser ? 'justify-end' : 'justify-start'">
    <div class="max-w-3xl flex flex-col" :class="isUser ? 'items-end' : 'items-start'">
      <!-- 来源标签 -->
      <div v-if="sourceLabel" class="text-xs text-gray-400 dark:text-gray-500 mb-1 px-1">
        {{ sourceLabel }}
      </div>

      <!-- 气泡内容 -->
      <div
        class="rounded-2xl px-4 py-3 shadow-sm break-words"
        :class="isUser
          ? 'bg-primary-600 text-white rounded-br-md'
          : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-800 dark:text-gray-100 rounded-bl-md'"
      >
        <div v-if="isUser" class="whitespace-pre-wrap">{{ message.content }}</div>
        <div v-else class="markdown-body" v-html="renderedHtml"></div>
      </div>

      <!-- 底部操作行：时间 · token · 复制 · 重新生成 -->
      <div
        class="flex items-center gap-2 mt-1 px-1 text-xs text-gray-400 dark:text-gray-500 h-5"
        :class="isUser ? 'flex-row-reverse' : 'flex-row'"
      >
        <!-- 时间（hover 可见完整时间） -->
        <span v-if="shortTime" :title="timeLabel" class="cursor-default">
          {{ shortTime }}
        </span>

        <!-- token 消耗 -->
        <span v-if="!isUser && message.token_usage" class="text-gray-400 dark:text-gray-500">
          · {{ message.token_usage }} tokens
        </span>

        <!-- 忠实度徽章（仅当前活跃的思考过程消息 + 有校验结果时显示） -->
        <span
          v-if="!isUser && isThinkingActive && chatStore.lastFaithfulness && chatStore.lastFaithfulness.score >= 0"
          class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full text-[10px] font-semibold"
          :class="{
            'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300': chatStore.lastFaithfulness.score >= 0.8,
            'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300': chatStore.lastFaithfulness.score >= 0.5 && chatStore.lastFaithfulness.score < 0.8,
            'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300': chatStore.lastFaithfulness.score < 0.5,
          }"
          :title="`忠实度: ${Math.round(chatStore.lastFaithfulness.score * 100)}% (${chatStore.lastFaithfulness.supported_claims}/${chatStore.lastFaithfulness.total_claims} 条声明有据可查)`"
        >
          <ShieldCheck :size="10" />
          {{ Math.round(chatStore.lastFaithfulness.score * 100) }}%
        </span>

        <!-- 思考过程查看按钮 -->
        <button
          v-if="!isUser && hasStoredTrace"
          @click="viewTraceOfThisMessage"
          class="flex items-center gap-1 transition-all rounded px-1.5 py-0.5 cursor-pointer text-xs"
          :class="isThinkingActive
            ? 'text-primary-600 dark:text-primary-400 bg-primary-50 dark:bg-primary-950/40 font-semibold border border-primary-200 dark:border-primary-800'
            : 'text-gray-400 dark:text-gray-500 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-gray-100 dark:hover:bg-gray-800'"
          title="点击在右侧面板查看本条消息的完整思考与工具调用链路"
        >
          <Sparkles :size="10" :class="isThinkingActive ? 'animate-pulse text-primary-500' : ''" />
          <span>思考过程</span>
        </button>

        <!-- 操作按钮组 hover 时显示 -->
        <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            class="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            title="复制消息内容"
            @click="copyContent"
          >
            <Check v-if="copied" :size="13" class="text-green-600" />
            <Copy v-else :size="13" />
          </button>
          <button
            v-if="isLastAssistant"
            class="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            title="重新生成回答"
            @click="emit('regenerate')"
          >
            <RotateCcw :size="13" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Markdown 渲染样式微调 */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  font-weight: 600;
  margin: 0.8em 0 0.4em;
}
.markdown-body :deep(h1) { font-size: 1.4em; }
.markdown-body :deep(h2) { font-size: 1.2em; }
.markdown-body :deep(h3) { font-size: 1.05em; }
.markdown-body :deep(p) { margin: 0.5em 0; line-height: 1.65; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0.5em 0;
  padding-left: 1.5em;
}
.markdown-body :deep(li) { margin: 0.2em 0; }
.markdown-body :deep(code:not(pre code)) {
  background: rgb(243 244 246);
  padding: 0.1em 0.4em;
  border-radius: 4px;
  font-size: 0.9em;
  color: rgb(67 56 202);
}
/* 暗色模式下行内 code / link / blockquote 颜色微调 */
:global(html.dark) .markdown-body :deep(code:not(pre code)) {
  background: rgb(55 65 81);  /* gray-700 */
  color: rgb(165 180 252);    /* indigo-300 */
}
:global(html.dark) .markdown-body :deep(a) {
  color: rgb(165 180 252);
}
:global(html.dark) .markdown-body :deep(blockquote) {
  border-left-color: rgb(75 85 99);
  color: rgb(156 163 175);
}
.markdown-body :deep(pre.hljs) {
  background: rgb(31 41 55);
  color: rgb(229 231 235);
  padding: 0.75em 1em;
  border-radius: 8px;
  margin: 0.5em 0;
  overflow-x: auto;
  font-size: 0.85em;
}
.markdown-body :deep(pre.hljs code) {
  background: transparent !important;
  color: inherit;
  padding: 0;
}
.markdown-body :deep(a) {
  color: rgb(79 70 229);
  text-decoration: underline;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid rgb(209 213 219);
  padding-left: 0.8em;
  color: rgb(107 114 128);
  margin: 0.5em 0;
}
.markdown-body :deep(strong) { font-weight: 600; }
</style>
