<script setup lang="ts">
/**
 * 对话主页面
 *
 * 三栏布局：会话列表 | 消息区 | 思考过程
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowDown, Check, ChevronLeft, ChevronRight, Library, Pencil, Plus, Search, Sparkles, Trash2, X } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import MessageBubble from '@/components/MessageBubble.vue'
import SkeletonList from '@/components/SkeletonList.vue'
import ThinkingTrace from '@/components/ThinkingTrace.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useShortcut } from '@/composables/useShortcuts'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'

const { confirm } = useConfirm()

const chat = useChatStore()
const kb = useKnowledgeStore()

const inputText = ref('')
const messagesRef = ref<HTMLDivElement | null>(null)
const showNewSessionModal = ref(false)
const newSessionTitle = ref('')
const newSessionKbId = ref<number | null>(null)
const showThinking = ref(false)  // 默认折叠，让消息区获得最大可用空间
const errorMsg = ref('')

// 会话搜索过滤
const searchKeyword = ref('')
const filteredSessions = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return chat.sessions
  return chat.sessions.filter((s) => s.title.toLowerCase().includes(kw))
})

// 会话重命名 inline edit 状态
const renamingSessionId = ref<number | null>(null)
const renameInput = ref('')

// "滚到底部" 浮动按钮：用户向上滚动时显示
const showScrollToBottom = ref(false)
function handleScroll() {
  if (!messagesRef.value) return
  const el = messagesRef.value
  // 距离底部超过 200px 则显示按钮
  const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
  showScrollToBottom.value = distanceFromBottom > 200
}
function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTo({ top: messagesRef.value.scrollHeight, behavior: 'smooth' })
  }
}

// ---------- 全局快捷键 ----------
// Ctrl+K 打开新建对话弹窗
useShortcut('ctrl+k', () => {
  showNewSessionModal.value = true
})
// Ctrl+/ 切换思考过程面板
useShortcut('ctrl+/', () => {
  showThinking.value = !showThinking.value
})
// Esc 关闭新建对话弹窗（允许在 input 中触发，因为弹窗内有 input）
useShortcut(
  'esc',
  () => {
    if (showNewSessionModal.value) showNewSessionModal.value = false
  },
  { allowInInputs: true },
)

onMounted(async () => {
  await Promise.all([chat.fetchSessions(), kb.fetchKnowledgeBases()])
  // 默认选中最近的会话
  if (chat.sessions.length > 0 && !chat.activeSessionId) {
    await chat.selectSession(chat.sessions[0].id)
  }
})

// 消息变化时自动滚到底部
watch(
  () => chat.messages.length,
  () => nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  }),
)

const activeKbName = computed(() => {
  const kbId = chat.activeSession?.kb_id
  if (!kbId) return null
  const item = kb.knowledgeBases.find((k) => k.id === kbId)
  return item?.name ?? `#${kbId}`
})

async function handleSend() {
  const text = inputText.value.trim()
  if (!text || !chat.activeSessionId || chat.sending) return
  inputText.value = ''
  errorMsg.value = ''
  try {
    // 默认走 SSE 流式（打字机效果），出错降级到普通发送
    await chat.sendMessageStream(text)
  } catch (e: any) {
    const msg = e?.message || '发送失败'
    errorMsg.value = msg
    toast.error(msg)
  }
}

async function handleNewSession() {
  showNewSessionModal.value = false
  const title = newSessionTitle.value.trim() || '新对话'
  await chat.createSession(title, newSessionKbId.value)
  newSessionTitle.value = ''
  newSessionKbId.value = null
}

async function handleDelete(sessionId: number) {
  const session = chat.sessions.find((s) => s.id === sessionId)
  const ok = await confirm({
    title: '删除会话',
    message: `确定要删除“${session?.title ?? '该会话'}”吗？会话历史将被永久清除且不可恢复。`,
    confirmText: '删除',
    variant: 'danger',
  })
  if (!ok) return
  await chat.deleteSession(sessionId)
  toast.success('会话已删除')
}

async function handleSelect(sessionId: number) {
  // 重命名状态时点击其它会话需先取消编辑
  if (renamingSessionId.value !== null && renamingSessionId.value !== sessionId) {
    cancelRename()
  }
  await chat.selectSession(sessionId)
}

// ---------- 会话重命名（inline edit） ----------
function startRename(sessionId: number, currentTitle: string) {
  renamingSessionId.value = sessionId
  renameInput.value = currentTitle
  // 下一帧 input 渲染后聚焦并全选
  nextTick(() => {
    const inputEl = document.querySelector<HTMLInputElement>(`[data-rename-input="${sessionId}"]`)
    if (inputEl) {
      inputEl.focus()
      inputEl.select()
    }
  })
}

async function saveRename() {
  if (renamingSessionId.value === null) return
  const newTitle = renameInput.value.trim()
  const sid = renamingSessionId.value
  // 提前重置编辑状态，避免抖动
  renamingSessionId.value = null
  if (!newTitle) {
    toast.error('标题不能为空')
    return
  }
  // 标题没改就不调 API
  const session = chat.sessions.find((s) => s.id === sid)
  if (session && session.title === newTitle) return
  try {
    await chat.updateSession(sid, { title: newTitle })
    toast.success('会话已重命名')
  } catch (e: any) {
    toast.error(`重命名失败: ${e?.message ?? '未知错误'}`)
  }
}

function cancelRename() {
  renamingSessionId.value = null
  renameInput.value = ''
}

// ---------- 重新生成回答 ----------
// 找到当前会话最后一条 user 消息，重新发送（不会重复创建消息行，由后端追加新的 assistant 回复）
async function regenerateLastAnswer() {
  if (chat.sending) return
  // 倒序找最后一条 user 消息
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

function onKeyDown(e: KeyboardEvent) {
  // Enter 发送，Shift+Enter 换行
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    handleSend()
  }
}
</script>

<template>
  <div class="flex h-full">
    <!-- 第一栏：会话列表 -->
    <div class="w-64 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col">
      <div class="p-3 border-b border-gray-200 dark:border-gray-800 space-y-2">
        <button
          class="w-full py-2 px-3 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors flex items-center justify-center gap-1.5"
          title="快捷键: Ctrl+K"
          @click="showNewSessionModal = true"
        >
          <Plus :size="16" :stroke-width="2.5" />
          <span>新建对话</span>
          <kbd class="hidden lg:inline-block ml-1 px-1.5 py-0.5 text-[10px] font-mono bg-primary-700/30 rounded">⌘K</kbd>
        </button>

        <!-- 会话搜索 -->
        <div class="relative">
          <Search :size="14" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            v-model="searchKeyword"
            type="text"
            placeholder="搜索会话..."
            class="w-full pl-8 pr-7 py-1.5 text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
          />
          <button
            v-if="searchKeyword"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            @click="searchKeyword = ''"
          >
            <X :size="12" />
          </button>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        <!-- 初次加载骨架屏 -->
        <SkeletonList
          v-if="chat.sessionsLoading && chat.sessions.length === 0"
          :rows="5"
          item-class="h-9 w-full"
          class="px-1"
        />
        <div v-else-if="chat.sessions.length === 0" class="text-center text-sm text-gray-400 py-8">
          暂无对话<br>点击上方按钮创建
        </div>
        <div v-else-if="filteredSessions.length === 0" class="text-center text-sm text-gray-400 py-8">
          没有匹配的会话
        </div>

        <div
          v-for="s in filteredSessions"
          :key="s.id"
          class="group flex items-center justify-between gap-1 px-3 py-2 rounded-lg cursor-pointer text-sm transition-colors"
          :class="chat.activeSessionId === s.id
            ? 'bg-primary-100 dark:bg-primary-900/40 text-primary-800 dark:text-primary-200'
            : 'text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800'"
          @click="handleSelect(s.id)"
          @dblclick="startRename(s.id, s.title)"
        >
          <!-- 重命名状态：input -->
          <input
            v-if="renamingSessionId === s.id"
            v-model="renameInput"
            :data-rename-input="s.id"
            type="text"
            class="flex-1 px-1.5 py-0.5 text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-primary-500 rounded outline-none ring-2 ring-primary-200 dark:ring-primary-900/40"
            @click.stop
            @keydown.enter.prevent="saveRename"
            @keydown.esc.prevent="cancelRename"
            @blur="saveRename"
          />
          <!-- 普通状态：标题 + hover 操作按钮 -->
          <template v-else>
            <span class="truncate flex-1" :title="s.title">{{ s.title }}</span>
            <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                class="text-gray-400 hover:text-primary-600"
                title="重命名（也可双击）"
                @click.stop="startRename(s.id, s.title)"
              >
                <Pencil :size="13" />
              </button>
              <button
                class="text-gray-400 hover:text-red-500"
                title="删除会话"
                @click.stop="handleDelete(s.id)"
              >
                <Trash2 :size="13" />
              </button>
            </div>
          </template>
        </div>
      </div>
    </div>

    <!-- 第二栏：消息区 -->
    <div class="flex-1 flex flex-col min-w-0 bg-white dark:bg-gray-950">
      <!-- 顶部 -->
      <div class="h-14 px-5 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between flex-shrink-0">
        <div class="min-w-0">
          <div class="text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
            {{ chat.activeSession?.title ?? '请选择或创建一个会话' }}
          </div>
          <div v-if="activeKbName" class="text-xs text-blue-600 dark:text-blue-400 mt-0.5 flex items-center gap-1">
            <Library :size="12" :stroke-width="2" />
            <span>关联知识库：{{ activeKbName }}</span>
          </div>
        </div>
        <button
          class="px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors"
          :class="showThinking
            ? 'bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 hover:bg-primary-100 dark:hover:bg-primary-900/50'
            : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'"
          :title="showThinking ? '隐藏思考过程' : '查看 Agent 完整推理链路'"
          @click="showThinking = !showThinking"
        >
          <Sparkles :size="14" :stroke-width="2" />
          <span>思考过程</span>
          <component :is="showThinking ? ChevronRight : ChevronLeft" :size="14" class="text-gray-400" />
        </button>
      </div>

      <!-- 消息流（relative 容器供"滚到底部"按钮定位） -->
      <div class="flex-1 relative overflow-hidden">
        <div
          ref="messagesRef"
          class="absolute inset-0 overflow-y-auto px-6 py-6 space-y-4"
          @scroll="handleScroll"
        >
          <div v-if="!chat.activeSessionId" class="h-full flex items-center justify-center text-gray-400 dark:text-gray-500">
            请选择或创建一个会话开始对话
          </div>
          <template v-else>
            <div v-if="chat.messages.length === 0" class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
              还没有消息，说点什么吧
            </div>
            <MessageBubble
              v-for="(m, idx) in chat.messages"
              :key="m.id"
              :message="m"
              :is-last-assistant="m.role === 'assistant' && idx === chat.messages.length - 1 && !chat.sending"
              @regenerate="regenerateLastAnswer"
            />
            <div v-if="chat.sending" class="flex justify-start">
              <div class="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-2xl rounded-bl-md px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                <span class="inline-flex gap-1">
                  <span class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0s"></span>
                  <span class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.15s"></span>
                  <span class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style="animation-delay: 0.3s"></span>
                </span>
                Agent 正在思考...
              </div>
            </div>
          </template>
        </div>

        <!-- 滚到底部浮动按钮（仅当用户向上滚动时显示） -->
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
            class="absolute bottom-4 left-1/2 -translate-x-1/2 w-10 h-10 rounded-full bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-lg flex items-center justify-center text-gray-600 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-900/30 transition-colors z-10"
            title="滚到最新消息"
            @click="scrollToBottom"
          >
            <ArrowDown :size="18" :stroke-width="2" />
          </button>
        </transition>
      </div>

      <!-- 错误提示 -->
      <div v-if="errorMsg" class="px-6 py-2 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-xs flex items-center justify-between">
        <span>{{ errorMsg }}</span>
        <button class="text-red-600 hover:text-red-800" @click="errorMsg = ''">
          <X :size="14" />
        </button>
      </div>

      <!-- 输入区 -->
      <div class="border-t border-gray-200 dark:border-gray-800 p-4 flex-shrink-0">
        <div class="flex gap-2">
          <textarea
            v-model="inputText"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            rows="2"
            class="flex-1 resize-none px-3 py-2 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-300 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent placeholder:text-gray-400 dark:placeholder:text-gray-500"
            :disabled="!chat.activeSessionId || chat.sending"
            @keydown="onKeyDown"
          ></textarea>
          <button
            class="px-5 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed self-end"
            :disabled="!inputText.trim() || !chat.activeSessionId || chat.sending"
            @click="handleSend"
          >
            发送
          </button>
        </div>
      </div>
    </div>

    <!-- 第三栏：思考过程（默认折叠，按钮唤起，带滑动过渡） -->
    <transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 translate-x-8"
      enter-to-class="opacity-100 translate-x-0"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-x-0"
      leave-to-class="opacity-0 translate-x-8"
    >
      <div v-if="showThinking" class="w-96 flex-shrink-0">
        <ThinkingTrace />
      </div>
    </transition>
  </div>

  <!-- 新建会话弹窗 -->
  <div
    v-if="showNewSessionModal"
    class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    @click.self="showNewSessionModal = false"
  >
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 w-96 space-y-4">
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">新建对话</h3>

      <div>
        <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">会话标题（可选）</label>
        <input
          v-model="newSessionTitle"
          type="text"
          placeholder="留空则用首条消息作为标题"
          class="w-full px-3 py-2 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-300 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 placeholder:text-gray-400 dark:placeholder:text-gray-500"
        />
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">关联知识库（可选，启用 RAG）</label>
        <select
          v-model="newSessionKbId"
          class="w-full px-3 py-2 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-300 dark:border-gray-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option :value="null">（不关联，仅闲聊/调工具）</option>
          <option v-for="k in kb.knowledgeBases" :key="k.id" :value="k.id">
            {{ k.name }}（{{ k.document_count }} 个文档）
          </option>
        </select>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button class="px-4 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200" @click="showNewSessionModal = false">
          取消
        </button>
        <button
          class="px-4 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          @click="handleNewSession"
        >
          创建
        </button>
      </div>
    </div>
  </div>
</template>
