<script setup lang="ts">
/**
 * 对话主页面 (重构壳组件)
 *
 * 仅负责状态路由与全局调度，具体 UI 下发至子组件：
 * 1. ChatSidebar: 左侧会话列表、搜索分组、增删改
 * 2. ChatHeader: 顶栏状态展示及控制
 * 3. ChatSummaryPanel: 摘要信息卡片
 * 4. ChatMessageList: 核心消息滚动流
 * 5. ChatApprovalPanel: 敏感工具拦截审批卡片
 * 6. ChatInputArea: 底部聊天框
 * 7. ChatCreateModal: 新建会话弹窗
 */
import { computed, onMounted, ref } from 'vue'
import { X } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import ThinkingTrace from '@/components/ThinkingTrace.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useShortcut } from '@/composables/useShortcuts'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'

import ChatSidebar from '@/components/chat/ChatSidebar.vue'
import ChatHeader from '@/components/chat/ChatHeader.vue'
import ChatSummaryPanel from '@/components/chat/ChatSummaryPanel.vue'
import ChatMessageList from '@/components/chat/ChatMessageList.vue'
import ChatApprovalPanel from '@/components/chat/ChatApprovalPanel.vue'
import ChatInputArea from '@/components/chat/ChatInputArea.vue'
import ChatCreateModal from '@/components/chat/ChatCreateModal.vue'

const { confirm } = useConfirm()
const chat = useChatStore()
const kb = useKnowledgeStore()

const showNewSessionModal = ref(false)
const showThinking = ref(false)  // 默认折叠
const showSummary = ref(false)
const sidebarCollapsed = ref(true)
const errorMsg = ref('')

// ----- 衍生状态 -----
const activeKbName = computed(() => {
  const kbId = chat.activeSession?.kb_id
  if (!kbId) return null
  const item = kb.knowledgeBases.find((k) => k.id === kbId)
  return item?.name ?? `#${kbId}`
})

const sessionTotalTokens = computed(() => {
  return chat.messages
    .filter((m) => m.role === 'assistant' && m.token_usage)
    .reduce((sum, m) => sum + (m.token_usage || 0), 0)
})

// ----- 全局快捷键 -----
useShortcut('ctrl+k', () => { showNewSessionModal.value = true })
useShortcut('ctrl+/', () => { showThinking.value = !showThinking.value })
useShortcut('esc', () => { if (showNewSessionModal.value) showNewSessionModal.value = false }, { allowInInputs: true })

onMounted(async () => {
  await Promise.all([chat.fetchSessions(), kb.fetchKnowledgeBases()])
  if (chat.sessions.length > 0 && !chat.activeSessionId) {
    await chat.selectSession(chat.sessions[0].id)
  }
})

// ----- 侧边栏交互 -----
async function handleSelectSession(id: number) {
  showSummary.value = false
  await chat.selectSession(id)
}

async function handleDeleteSession(id: number) {
  const session = chat.sessions.find((s) => s.id === id)
  const ok = await confirm({
    title: '删除会话',
    message: `确定要删除“${session?.title ?? '该会话'}”吗？会话历史将被永久清除且不可恢复。`,
    confirmText: '删除',
    variant: 'danger',
  })
  if (!ok) return
  await chat.deleteSession(id)
  toast.success('会话已删除')
}

async function handleRenameSession(id: number, newTitle: string) {
  const session = chat.sessions.find((s) => s.id === id)
  if (session && session.title === newTitle) return
  try {
    await chat.updateSession(id, { title: newTitle })
    toast.success('会话已重命名')
  } catch (e: any) {
    toast.error(`重命名失败: ${e?.message ?? '未知错误'}`)
  }
}

async function handleCreateSession(title: string, kbId: number | null) {
  showNewSessionModal.value = false
  await chat.createSession(title, kbId)
}

// ----- 聊天流交互 -----
async function handleSend(text: string) {
  errorMsg.value = ''
  try {
    if (!chat.activeSessionId) {
      await chat.createSession('新对话')
    }
    await chat.sendMessageStream(text)
  } catch (e: any) {
    errorMsg.value = e?.message || '发送失败'
    toast.error(errorMsg.value)
  }
}

async function regenerateLastAnswer() {
  if (chat.sending) return
  const lastUserMsg = [...chat.messages].reverse().find((m) => m.role === 'user')
  if (!lastUserMsg) {
    toast.error('找不到可重新生成的提问')
    return
  }
  try {
    await chat.sendMessageStream(lastUserMsg.content)
    toast.success('已重新生成回答')
  } catch (e: any) {
    toast.error(`重新生成失败: ${e?.message ?? '未知错误'}`)
  }
}

// ----- 工具审批 -----
async function handleApproval(action: 'approve' | 'reject') {
  try {
    await chat.resumeApproval(action)
  } catch (e: any) {
    toast.error(`审批操作失败: ${e?.message ?? '未知错误'}`)
  }
}
</script>

<template>
  <div class="flex h-full bg-zinc-50 dark:bg-zinc-900">
    <!-- 移动端会话列表遮罩层 -->
    <div
      v-if="!sidebarCollapsed"
      class="md:hidden fixed inset-0 bg-black/40 backdrop-blur-xs z-40 transition-opacity"
      @click="sidebarCollapsed = true"
    ></div>

    <!-- 第一栏：侧边栏 -->
    <transition
      enter-active-class="transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]"
      enter-from-class="opacity-0 -translate-x-4 max-w-0"
      enter-to-class="opacity-100 translate-x-0 max-w-64"
      leave-active-class="transition-all duration-400 ease-[cubic-bezier(0.16,1,0.3,1)]"
      leave-from-class="opacity-100 translate-x-0 max-w-64"
      leave-to-class="opacity-0 -translate-x-4 max-w-0"
    >
      <ChatSidebar
        v-if="!sidebarCollapsed"
        :sessions="chat.sessions"
        :active-session-id="chat.activeSessionId"
        :loading="chat.sessionsLoading"
        @select="handleSelectSession"
        @delete="handleDeleteSession"
        @create="showNewSessionModal = true"
        @rename="handleRenameSession"
      />
    </transition>

    <!-- 第二栏：主消息区 -->
    <div class="flex-1 flex flex-col min-w-0 bg-white dark:bg-zinc-950 transition-colors duration-200">
      <!-- 顶栏 -->
      <ChatHeader
        :sidebar-collapsed="sidebarCollapsed"
        :session-title="chat.activeSession?.title ?? '请选择或创建一个会话'"
        :active-kb-name="activeKbName"
        :has-summary="!!chat.activeSession?.summary"
        :show-summary="showSummary"
        :show-thinking="showThinking"
        @toggle-sidebar="sidebarCollapsed = !sidebarCollapsed"
        @toggle-summary="showSummary = !showSummary"
        @toggle-thinking="showThinking = !showThinking"
      />

      <!-- 摘要面板 -->
      <transition
        enter-active-class="transition-all duration-300 ease-out"
        enter-from-class="opacity-0 -translate-y-2 max-h-0"
        enter-to-class="opacity-100 translate-y-0 max-h-60"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="opacity-100 translate-y-0 max-h-60"
        leave-to-class="opacity-0 -translate-y-2 max-h-0"
      >
        <ChatSummaryPanel
          v-if="showSummary && chat.activeSession?.summary"
          :summary="chat.activeSession.summary"
          :created-at="chat.activeSession.created_at"
          :updated-at="chat.activeSession.updated_at"
          :total-tokens="sessionTotalTokens"
        />
      </transition>

      <!-- 核心消息流 -->
      <ChatMessageList
        :active-session-id="chat.activeSessionId"
        :messages="chat.messages"
        :sending="chat.sending"
        @regenerate="regenerateLastAnswer"
        @stop-generating="chat.stopGenerating"
      />

      <!-- 敏感工具审批弹窗 -->
      <transition
        enter-active-class="transition-all duration-300 ease-out"
        enter-from-class="opacity-0 translate-y-4"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 translate-y-4"
      >
        <ChatApprovalPanel
          v-if="chat.pendingApproval"
          :approval="chat.pendingApproval"
          :sending="chat.sending"
          @approve="handleApproval('approve')"
          @reject="handleApproval('reject')"
        />
      </transition>

      <!-- 错误提示带 -->
      <div v-if="errorMsg" class="px-6 py-2.5 bg-red-50 dark:bg-red-950/40 border-t border-red-200/30 text-red-700 dark:text-red-400 text-[10px] font-bold flex items-center justify-between">
        <span>错误信息：{{ errorMsg }}</span>
        <button class="text-red-500 hover:text-red-700 transition-colors" @click="errorMsg = ''">
          <X :size="12" />
        </button>
      </div>

      <!-- 底部输入区 -->
      <ChatInputArea
        :sending="chat.sending"
        @send="handleSend"
        @stop="chat.stopGenerating"
      />
    </div>

    <!-- 移动端思考过程遮罩层 -->
    <div
      v-if="showThinking"
      class="md:hidden fixed inset-0 bg-black/40 backdrop-blur-xs z-40 transition-opacity"
      @click="showThinking = false"
    ></div>

    <!-- 第三栏：思考过程面板 -->
    <transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 translate-x-8"
      enter-to-class="opacity-100 translate-x-0"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-x-0"
      leave-to-class="opacity-0 translate-x-8"
    >
      <div v-if="showThinking" class="w-80 md:w-96 fixed md:relative inset-y-0 right-0 z-50 bg-zinc-50 dark:bg-zinc-950 border-l border-gray-200/50 dark:border-gray-800/40 shadow-2xl md:shadow-none flex flex-col">
        <ThinkingTrace />
      </div>
    </transition>
  </div>

  <!-- 新建对话弹窗 -->
  <transition
    enter-active-class="transition-all duration-200 ease-out"
    enter-from-class="opacity-0 scale-95"
    enter-to-class="opacity-100 scale-100"
    leave-active-class="transition-all duration-150 ease-in"
    leave-from-class="opacity-100 scale-100"
    leave-to-class="opacity-0 scale-95"
  >
    <ChatCreateModal
      v-if="showNewSessionModal"
      :knowledge-bases="kb.knowledgeBases"
      @close="showNewSessionModal = false"
      @create="handleCreateSession"
    />
  </transition>
</template>
