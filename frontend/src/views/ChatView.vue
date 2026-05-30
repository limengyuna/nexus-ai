<script setup lang="ts">
/**
 * 对话主页面
 *
 * 三栏布局：会话列表 | 消息区 | 思考过程
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { ArrowDown, Check, ChevronDown, ChevronLeft, ChevronRight, FileText, Library, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Search, Sparkles, Trash2, X, Zap } from 'lucide-vue-next'
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
const showSummary = ref(false)
const sidebarCollapsed = ref(true)

// 会话累计 token
const sessionTotalTokens = computed(() => {
  return chat.messages
    .filter((m) => m.role === 'assistant' && m.token_usage)
    .reduce((sum, m) => sum + (m.token_usage || 0), 0)
})

// 估算当前活动（未归档）上下文窗口占用的 Token 数
const currentContextTokens = computed(() => {
  if (!chat.activeSessionId) return 0
  
  // 1. 系统基础提示词、时间、角色标签等开销 (约 100 tokens)
  let total = 100
  
  // 2. 注入历史摘要 (如已触发对话压缩)
  if (chat.activeSession?.summary) {
    total += Math.ceil(chat.activeSession.summary.length * 0.6)
  }
  
  // 3. L2 语义事实记忆注入（context_prep 从 ChromaDB 检索并以 system 消息注入）
  if (chat.lastRetrievedMemories && chat.lastRetrievedMemories.length > 0) {
    // 固定引导文本开销（约 40 tokens）
    total += 40
    for (const mem of chat.lastRetrievedMemories) {
      total += Math.ceil(mem.content.length * 0.6) + 10
    }
  }

  // 4. 注入未归档的活动消息
  const activeMessages = chat.messages.filter((m) => !m.is_archived)
  for (const m of activeMessages) {
    // 消息内容估算
    total += Math.ceil(m.content.length * 0.6)
    // 注入工具调用的结果数据估算
    if (m.tool_calls_json) {
      total += Math.ceil(JSON.stringify(m.tool_calls_json).length * 0.3)
    }
    // 基础消息包裹头
    total += 20
  }
  
  return total
})

// 模型单次上下文额度上限（以标准的 DeepSeek-V4 1M 极致上下文窗口为基准）
const contextLimit = 1000000
const currentContextPercent = computed(() => {
  return Math.min(Math.round((currentContextTokens.value / contextLimit) * 100), 100)
})

function formatTokens(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

// UTC 时间戳转本地时间显示
function formatLocalTime(utcStr: string | undefined | null): string {
  if (!utcStr) return ''
  const d = new Date(utcStr)
  return d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  })
}

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
  if (!text || chat.sending) return
  inputText.value = ''
  errorMsg.value = ''
  try {
    // 如果没有活跃会话，自动创建一个新会话
    if (!chat.activeSessionId) {
      await chat.createSession('新对话')
    }
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
  showSummary.value = false
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

// ---------- 工具审批操作 ----------
async function handleApproval(action: 'approve' | 'reject') {
  try {
    await chat.resumeApproval(action)
  } catch (e: any) {
    toast.error(`审批操作失败: ${e?.message ?? '未知错误'}`)
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
  <div class="flex h-full bg-[#f8fafc] dark:bg-[#07080d]">
    <!-- 第一栏：会话列表（引入毛玻璃与高感半透质感） -->
    <transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 -translate-x-4 max-w-0"
      enter-to-class="opacity-100 translate-x-0 max-w-64"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-x-0 max-w-64"
      leave-to-class="opacity-0 -translate-x-4 max-w-0"
    >
      <div v-if="!sidebarCollapsed" class="w-64 bg-white/50 dark:bg-[#0c0d14]/40 backdrop-blur-md border-r border-gray-200/50 dark:border-gray-800/40 flex flex-col flex-shrink-0">
        <div class="p-3.5 border-b border-gray-100/60 dark:border-gray-800/30 space-y-2.5">
          <!-- 新建对话按钮 -->
          <button
            class="w-full py-2 px-3 bg-gradient-to-r from-gray-800 to-gray-700 hover:from-gray-900 hover:to-gray-800 text-white text-xs font-semibold rounded-xl transition-all duration-200 flex items-center justify-center gap-1.5 btn-shine-effect shadow-md shadow-gray-800/5 active:scale-[0.98]"
            title="快捷键: Ctrl+K"
            @click="showNewSessionModal = true"
          >
            <Plus :size="14" :stroke-width="3" />
            <span>新建对话</span>
            <kbd class="hidden lg:inline-block ml-1 px-1.5 py-0.5 text-[9px] font-mono bg-primary-700/20 rounded font-bold">⌘K</kbd>
          </button>

          <!-- 会话搜索 -->
          <div class="relative">
            <Search :size="13" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              v-model="searchKeyword"
              type="text"
              placeholder="搜索会话..."
              class="w-full pl-8 pr-7 py-1.5 text-xs bg-white/80 dark:bg-gray-900/50 text-gray-700 dark:text-gray-200 border border-gray-200/70 dark:border-gray-800 rounded-xl focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 transition-all duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
            />
            <button
              v-if="searchKeyword"
              class="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
              @click="searchKeyword = ''"
            >
              <X :size="11" />
            </button>
          </div>
        </div>

        <!-- 列表滚动区 -->
        <div class="flex-1 overflow-y-auto px-2 py-2 space-y-1">
          <SkeletonList
            v-if="chat.sessionsLoading && chat.sessions.length === 0"
            :rows="5"
            item-class="h-9 w-full rounded-lg"
            class="px-1"
          />
          <div v-else-if="chat.sessions.length === 0" class="text-center text-xs text-gray-400/80 py-10 font-medium">
            暂无对话<br>点击上方按钮创建
          </div>
          <div v-else-if="filteredSessions.length === 0" class="text-center text-xs text-gray-400/80 py-10 font-medium">
            没有匹配的会话
          </div>

          <div
            v-for="s in filteredSessions"
            :key="s.id"
            class="group flex items-center justify-between gap-1.5 px-3 py-2 rounded-xl cursor-pointer text-xs font-semibold transition-all duration-200 border"
            :class="chat.activeSessionId === s.id
              ? 'bg-primary-500/10 dark:bg-primary-500/15 border-primary-500/20 text-primary-700 dark:text-primary-300 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100/60 dark:hover:bg-gray-800/40 border-transparent hover:text-gray-800 dark:hover:text-gray-200'"
            @click="handleSelect(s.id)"
            @dblclick="startRename(s.id, s.title)"
          >
            <!-- 重命名 -->
            <input
              v-if="renamingSessionId === s.id"
              v-model="renameInput"
              :data-rename-input="s.id"
              type="text"
              class="flex-1 px-2 py-0.5 text-xs bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 border border-primary-500 rounded-lg outline-none ring-4 ring-primary-500/10"
              @click.stop
              @keydown.enter.prevent="saveRename"
              @keydown.esc.prevent="cancelRename"
              @blur="saveRename"
            />
            <!-- 普通显示 -->
            <template v-else>
              <span class="truncate flex-1" :title="s.title">{{ s.title }}</span>
              <div class="flex items-center gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                <button
                  class="text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                  title="重命名（双击也可）"
                  @click.stop="startRename(s.id, s.title)"
                >
                  <Pencil :size="12" />
                </button>
                <button
                  class="text-gray-400 hover:text-red-500 transition-colors"
                  title="删除会话"
                  @click.stop="handleDelete(s.id)"
                >
                  <Trash2 :size="12" />
                </button>
              </div>
            </template>
          </div>
        </div>
      </div>
    </transition>

    <!-- 第二栏：消息区 -->
    <div class="flex-1 flex flex-col min-w-0 bg-[#fafcfd] dark:bg-[#08090d] transition-colors duration-200">
      <!-- 顶栏 -->
      <div class="h-14 px-5 bg-white/60 dark:bg-[#0c0d14]/60 backdrop-blur-md border-b border-gray-100/60 dark:border-gray-800/30 flex items-center justify-between flex-shrink-0 z-20">
        <div class="flex items-center gap-2.5 min-w-0">
          <!-- 侧边栏按钮 -->
          <button
            class="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100/80 dark:hover:bg-gray-800/40 transition-all flex-shrink-0 active:scale-95"
            :title="sidebarCollapsed ? '展开会话列表' : '收起会话列表'"
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <PanelLeftOpen v-if="sidebarCollapsed" :size="16" :stroke-width="2.5" />
            <PanelLeftClose v-else :size="16" :stroke-width="2.5" />
          </button>
          
          <div class="text-xs font-bold text-gray-700 dark:text-gray-200 truncate">
            {{ chat.activeSession?.title ?? '请选择或创建一个会话' }}
          </div>
          
          <div v-if="activeKbName" class="text-[10px] bg-blue-500/10 text-blue-600 dark:text-blue-400 px-2 py-0.5 rounded-full border border-blue-500/10 flex items-center gap-1 font-semibold">
            <Library :size="10" :stroke-width="2.5" />
            <span>知识库：{{ activeKbName }}</span>
          </div>
        </div>

        <div class="flex items-center gap-2">
          <!-- 对话摘要按钮 -->
          <button
            v-if="chat.activeSession?.summary"
            class="px-2.5 py-1.5 rounded-xl text-[10px] font-bold flex items-center gap-1 transition-colors border shadow-xs"
            :class="showSummary
              ? 'bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-400 hover:bg-amber-500/20'
              : 'bg-white dark:bg-gray-900 border-gray-200/50 dark:border-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'"
            title="查看 AI 对当前对话的理解摘要"
            @click="showSummary = !showSummary"
          >
            <FileText :size="12" :stroke-width="2.5" />
            <span>对话摘要</span>
            <ChevronDown :size="12" class="transition-transform duration-200" :class="showSummary ? 'rotate-180' : ''" />
          </button>
          
          <!-- 思考过程按钮 -->
          <button
            class="px-2.5 py-1.5 rounded-xl text-[10px] font-bold flex items-center gap-1 transition-colors border shadow-xs"
            :class="showThinking
              ? 'bg-primary-500/10 border-primary-500/20 text-primary-700 dark:text-primary-400 hover:bg-primary-500/20'
              : 'bg-white dark:bg-gray-900 border-gray-200/50 dark:border-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800'"
            :title="showThinking ? '隐藏思考过程' : '查看 Agent 完整推理链路'"
            @click="showThinking = !showThinking"
          >
            <Sparkles :size="12" :stroke-width="2.5" />
            <span>思考过程</span>
            <component :is="showThinking ? ChevronRight : ChevronLeft" :size="12" class="text-gray-400" />
          </button>
        </div>
      </div>

      <!-- 对话摘要面板 -->
      <transition
        enter-active-class="transition-all duration-300 ease-out"
        enter-from-class="opacity-0 -translate-y-2 max-h-0"
        enter-to-class="opacity-100 translate-y-0 max-h-60"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="opacity-100 translate-y-0 max-h-60"
        leave-to-class="opacity-0 -translate-y-2 max-h-0"
      >
        <div
          v-if="showSummary && chat.activeSession?.summary"
          class="px-5 py-3.5 bg-amber-500/5 dark:bg-amber-500/5 border-b border-amber-200/40 dark:border-amber-900/20 overflow-hidden"
        >
          <div class="flex items-start gap-2.5">
            <FileText :size="13" class="text-amber-600 dark:text-amber-400 mt-0.5 flex-shrink-0" />
            <div class="min-w-0 flex-1">
              <div class="text-[9px] font-bold text-amber-600/80 dark:text-amber-400/80 uppercase tracking-widest mb-1 font-outfit">AI MEMORY KEYWORDS</div>
              <p class="text-xs text-gray-600 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">{{ chat.activeSession.summary }}</p>
              <div class="mt-2.5 flex items-center gap-3 text-[9px] text-gray-400 dark:text-gray-500 font-medium">
                <span>创建时间：{{ formatLocalTime(chat.activeSession.created_at) }}</span>
                <span>更新时间：{{ formatLocalTime(chat.activeSession.updated_at) }}</span>
                <span v-if="sessionTotalTokens > 0" class="flex items-center gap-0.5 text-amber-600 dark:text-amber-400 font-semibold bg-amber-500/10 px-1.5 py-0.5 rounded">
                  <Zap :size="9" />
                  累计吞吐 {{ formatTokens(sessionTotalTokens) }} tokens
                </span>
              </div>
            </div>
          </div>
        </div>
      </transition>

      <!-- 消息列表滚动区 -->
      <div class="flex-1 relative overflow-hidden">
        <div
          ref="messagesRef"
          class="absolute inset-0 overflow-y-auto px-6 py-6 space-y-5"
          @scroll="handleScroll"
        >
          <div v-if="!chat.activeSessionId" class="h-full flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 font-medium text-xs space-y-2">
            <MessageSquare :size="24" class="text-gray-300 dark:text-gray-700 animate-pulse" />
            <span>请选择或创建一个会话开始对话</span>
          </div>
          <template v-else>
            <div v-if="chat.messages.length === 0" class="h-full flex flex-col items-center justify-center text-gray-400 dark:text-gray-500 font-medium text-xs space-y-2 py-12">
              <Sparkles :size="20" class="text-gray-300 dark:text-gray-700" />
              <span>还没有消息，向 NexusAI 智能体提问吧</span>
            </div>
            
            <MessageBubble
              v-for="(m, idx) in chat.messages"
              :key="m.id"
              :message="m"
              :is-last-assistant="m.role === 'assistant' && idx === chat.messages.length - 1 && !chat.sending"
              @regenerate="regenerateLastAnswer"
            />
            
            <!-- Agent 正在思考中的流光呼吸效果 -->
            <div v-if="chat.sending && !chat.messages.some(m => m.role === 'assistant' && m.id < 0 && m.content)" class="flex justify-start">
              <div class="bg-white/80 dark:bg-gray-900/60 backdrop-blur-md border border-gray-100 dark:border-gray-800 rounded-2xl rounded-bl-md px-4 py-3 text-xs text-gray-500 dark:text-gray-400 inline-flex items-center gap-3 shadow-sm obsidian-glow">
                <span class="inline-flex gap-1">
                  <span class="w-1.5 h-1.5 bg-primary-500 rounded-full animate-bounce" style="animation-delay: 0s"></span>
                  <span class="w-1.5 h-1.5 bg-primary-500 rounded-full animate-bounce" style="animation-delay: 0.15s"></span>
                  <span class="w-1.5 h-1.5 bg-primary-500 rounded-full animate-bounce" style="animation-delay: 0.3s"></span>
                </span>
                <span class="font-semibold">智能体正在思考多步协作方案...</span>
                <button
                  class="text-[10px] px-2 py-0.5 rounded-lg border border-red-200 text-red-600 hover:bg-red-50 dark:border-red-900/50 dark:text-red-400 dark:hover:bg-red-900/20 transition-all font-bold active:scale-95"
                  title="停止生成"
                  @click="chat.stopGenerating()"
                >停止</button>
              </div>
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
            class="absolute bottom-4 left-1/2 -translate-x-1/2 w-9 h-9 rounded-full bg-white/90 dark:bg-gray-800/90 border border-gray-200/60 dark:border-gray-700/60 shadow-lg flex items-center justify-center text-gray-500 dark:text-gray-300 hover:text-primary-600 dark:hover:text-primary-400 hover:bg-primary-50/50 dark:hover:bg-primary-950/40 transition-all active:scale-90 z-10 backdrop-blur-md"
            title="滚到最新消息"
            @click="scrollToBottom"
          >
            <ArrowDown :size="16" :stroke-width="2.5" />
          </button>
        </transition>
      </div>

      <!-- 工具审批卡片 -->
      <transition
        enter-active-class="transition-all duration-300 ease-out"
        enter-from-class="opacity-0 translate-y-4"
        enter-to-class="opacity-100 translate-y-0"
        leave-active-class="transition-all duration-200 ease-in"
        leave-from-class="opacity-100 translate-y-0"
        leave-to-class="opacity-0 translate-y-4"
      >
        <div v-if="chat.pendingApproval" class="mx-6 mb-4 rounded-2xl border border-amber-300/60 dark:border-amber-600/30 bg-amber-50/80 dark:bg-amber-950/20 backdrop-blur-md shadow-xl overflow-hidden obsidian-glow animate-pulse-subtle">
          <!-- 标题 -->
          <div class="flex items-center gap-2 px-4 py-3 bg-amber-100/50 dark:bg-amber-900/20 border-b border-amber-200/40 dark:border-amber-900/20">
            <span class="text-amber-500 text-base">⚠️</span>
            <span class="text-xs font-bold text-amber-800 dark:text-amber-300">Agent 请求执行敏感工具</span>
            <span class="ml-auto text-[9px] px-2 py-0.5 rounded-full bg-amber-200/60 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200 font-bold uppercase tracking-wider font-outfit">
              {{ (chat.pendingApproval.payload as any).tool_kind }}
            </span>
          </div>
          <!-- 内容 -->
          <div class="px-4 py-3 space-y-2.5">
            <div class="text-xs font-semibold text-gray-700 dark:text-gray-200">
              <span>{{ chat.pendingApproval.payload.message }}</span>
            </div>
            <div class="text-[10px] text-gray-500 dark:text-gray-400 font-medium">
              调用工具：<code class="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded font-mono text-[9px] font-bold text-gray-700 dark:text-gray-300">{{ (chat.pendingApproval.payload as any).tool_name }}</code>
            </div>
            <!-- 参数 -->
            <details class="text-[10px] font-semibold">
              <summary class="cursor-pointer text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors">查看参数详情</summary>
              <pre class="mt-1.5 p-2 bg-gray-100/50 dark:bg-gray-900/50 border border-gray-200/30 dark:border-gray-800/30 rounded-lg text-[9px] font-mono overflow-x-auto max-h-32 text-gray-600 dark:text-gray-400">{{ JSON.stringify((chat.pendingApproval.payload as any).arguments, null, 2) }}</pre>
            </details>
          </div>
          <!-- 按钮 -->
          <div class="flex items-center gap-3 px-4 py-3 border-t border-amber-200/40 dark:border-amber-900/20 bg-amber-50/20 dark:bg-amber-900/10">
            <button
              class="flex-1 py-1.5 text-xs font-bold rounded-lg bg-green-600 hover:bg-green-700 text-white transition-all shadow-md shadow-green-600/10 active:scale-[0.98] disabled:opacity-60"
              :disabled="chat.sending"
              @click="handleApproval('approve')"
            >
              ✓ 批准执行
            </button>
            <button
              class="flex-1 py-1.5 text-xs font-bold rounded-lg bg-red-50 dark:bg-red-950/20 hover:bg-red-100 dark:hover:bg-red-900/40 text-red-700 dark:text-red-400 border border-red-200/40 dark:border-red-900/30 transition-all active:scale-[0.98] disabled:opacity-60"
              :disabled="chat.sending"
              @click="handleApproval('reject')"
            >
              ✗ 拒绝执行
            </button>
          </div>
        </div>
      </transition>

      <!-- 错误提示 -->
      <div v-if="errorMsg" class="px-6 py-2.5 bg-red-50 dark:bg-red-950/40 border-t border-red-200/30 text-red-700 dark:text-red-400 text-[10px] font-bold flex items-center justify-between">
        <span>错误信息：{{ errorMsg }}</span>
        <button class="text-red-500 hover:text-red-700 transition-colors" @click="errorMsg = ''">
          <X :size="12" />
        </button>
      </div>

      <!-- 输入区 -->
      <div class="border-t border-gray-100 dark:border-gray-800 p-4 flex-shrink-0 bg-white/40 dark:bg-gray-950/20">
        
        <!-- 活动上下文窗口指示条 (Cursor IDE 极客风格，重新设计并高大上外显) -->
        <div class="flex items-center justify-between text-[10px] mb-2 text-gray-500 dark:text-gray-400 select-none px-2.5 py-1.5 bg-gray-100/50 dark:bg-gray-900/40 border border-gray-200/40 dark:border-gray-800/40 rounded-xl">
          <div class="flex items-center gap-1.5 font-semibold">
            <Zap :size="11" class="text-amber-500 flex-shrink-0" :class="chat.sending ? 'animate-pulse' : ''" />
            <span class="font-bold tracking-wide">上下文窗口已用：</span>
            <span class="font-bold font-mono" :class="currentContextTokens > 800000 ? 'text-red-500' : currentContextTokens > 500000 ? 'text-amber-500' : 'text-primary-600 dark:text-primary-400'">
              {{ currentContextPercent }}% ({{ formatTokens(currentContextTokens) }} / 1.0M tokens)
            </span>
          </div>
          <!-- 极客风细条进度槽 -->
          <div class="w-24 h-1 bg-gray-200 dark:bg-gray-800 rounded-full overflow-hidden flex-shrink-0 ml-2">
            <div
              class="h-full rounded-full transition-all duration-500 bg-gradient-to-r"
              :class="currentContextPercent > 80 ? 'from-red-500 to-pink-500' : currentContextPercent > 50 ? 'from-amber-500 to-orange-500' : 'from-primary-500 to-indigo-500'"
              :style="{ width: `${currentContextPercent}%` }"
            ></div>
          </div>
        </div>

        <!-- 文本域与动作按钮 -->
        <div class="flex gap-2.5">
          <textarea
            v-model="inputText"
            placeholder="输入消息，Enter 发送，Shift+Enter 换行"
            rows="2"
            class="flex-1 resize-none px-4 py-2.5 bg-white/80 dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-xl text-xs focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 transition-all duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500"
            :disabled="chat.sending"
            @keydown="onKeyDown"
          ></textarea>
          
          <!-- 双态发送/停止按钮 -->
          <button
            v-if="!chat.sending"
            class="px-5 py-2 bg-gradient-to-r from-gray-800 to-gray-700 hover:from-gray-900 hover:to-gray-800 text-white text-xs font-bold rounded-xl transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed self-end btn-shine-effect shadow-md shadow-gray-800/5 active:scale-95"
            :disabled="!inputText.trim()"
            @click="handleSend"
          >
            发送
          </button>
          <button
            v-else
            class="px-5 py-2 bg-gradient-to-r from-red-500 to-pink-500 hover:from-red-600 hover:to-pink-600 text-white text-xs font-bold rounded-xl transition-all duration-200 self-end flex items-center gap-1.5 shadow-md shadow-red-500/5 active:scale-95"
            title="停止生成（智能体将在临近步骤完成时退出）"
            @click="chat.stopGenerating()"
          >
            <span class="w-2 h-2 bg-white rounded-xs animate-pulse"></span>
            停止
          </button>
        </div>
      </div>
    </div>

    <!-- 第三栏：思考过程（带透光半透与平滑抽屉） -->
    <transition
      enter-active-class="transition-all duration-300 ease-out"
      enter-from-class="opacity-0 translate-x-8"
      enter-to-class="opacity-100 translate-x-0"
      leave-active-class="transition-all duration-200 ease-in"
      leave-from-class="opacity-100 translate-x-0"
      leave-to-class="opacity-0 translate-x-8"
    >
      <div v-if="showThinking" class="w-96 flex-shrink-0 border-l border-gray-200/50 dark:border-gray-800/40 bg-white/40 dark:bg-[#0c0d14]/40 backdrop-blur-md">
        <ThinkingTrace />
      </div>
    </transition>
  </div>

  <!-- 新建会话高感弹窗 -->
  <transition
    enter-active-class="transition-all duration-200 ease-out"
    enter-from-class="opacity-0 scale-95"
    enter-to-class="opacity-100 scale-100"
    leave-active-class="transition-all duration-150 ease-in"
    leave-from-class="opacity-100 scale-100"
    leave-to-class="opacity-0 scale-95"
  >
    <div
      v-if="showNewSessionModal"
      class="fixed inset-0 bg-black/40 dark:bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 px-4"
      @click.self="showNewSessionModal = false"
    >
      <div class="bg-white/95 dark:bg-[#0c0d14]/95 backdrop-blur-xl rounded-2xl border border-white/20 dark:border-white/5 shadow-2xl p-6 w-full max-w-sm space-y-4 obsidian-glow">
        <h3 class="text-sm font-extrabold text-gray-800 dark:text-gray-100 font-outfit tracking-wide uppercase">新建智能对话会话</h3>

        <div>
          <label class="block text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase mb-1.5 ml-0.5">会话标题（可选）</label>
          <input
            v-model="newSessionTitle"
            type="text"
            placeholder="留空则以首条提问为标题"
            class="w-full px-3 py-2 bg-white dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-xl text-xs focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 transition-all placeholder:text-gray-400 dark:placeholder:text-gray-500"
          />
        </div>

        <div>
          <label class="block text-[10px] font-bold text-gray-500 dark:text-gray-400 uppercase mb-1.5 ml-0.5">关联知识库库管道（可选，启用 RAG）</label>
          <select
            v-model="newSessionKbId"
            class="w-full px-3 py-2 bg-white dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-xl text-xs focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 transition-all"
          >
            <option :value="null">（不关联，仅通用闲聊或协作）</option>
            <option v-for="k in kb.knowledgeBases" :key="k.id" :value="k.id">
              {{ k.name }}（{{ k.document_count }} 篇文档数据）
            </option>
          </select>
        </div>

        <div class="flex justify-end gap-2.5 pt-2">
          <button class="px-3.5 py-1.5 text-xs font-bold text-gray-500 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 transition-colors" @click="showNewSessionModal = false">
            取消
          </button>
          <button
            class="px-4 py-1.5 text-xs font-bold bg-gradient-to-r from-gray-800 to-gray-700 hover:from-gray-900 hover:to-gray-800 text-white rounded-xl transition-all shadow-md active:scale-95"
            @click="handleNewSession"
          >
            创建会话
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>
