/**
 * 对话状态管理 (Pinia Store)
 *
 * 维护：当前会话列表、当前激活会话、当前消息列表、当前思考过程
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type {
  ChatMessage,
  ChatResponse,
  ChatSession,
  RetrievedDoc,
  ToolCall,
  TraceStep,
} from '@/api/chat'
import * as chatApi from '@/api/chat'

export const useChatStore = defineStore('chat', () => {
  // ---------- 状态 ----------
  const sessions = ref<ChatSession[]>([])
  const sessionsLoading = ref(false)  // 会话列表首次加载状态（用于骨架屏）
  const activeSessionId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const sending = ref(false)

  // 最近一次回复的"思考过程"快照
  const lastIntent = ref('')
  const lastRouteReason = ref('')
  const lastSkillUsed = ref<string | null>(null)
  const lastTrace = ref<TraceStep[]>([])
  const lastToolCalls = ref<ToolCall[]>([])
  const lastRetrievedDocs = ref<RetrievedDoc[]>([])

  // ---------- 计算属性 ----------
  const activeSession = computed(() =>
    sessions.value.find((s) => s.id === activeSessionId.value) ?? null,
  )

  // ---------- Actions ----------
  async function fetchSessions() {
    sessionsLoading.value = true
    try {
      sessions.value = await chatApi.listSessions()
    } finally {
      sessionsLoading.value = false
    }
  }

  async function selectSession(sessionId: number | null) {
    activeSessionId.value = sessionId
    messages.value = []
    clearTrace()
    if (sessionId !== null) {
      messages.value = await chatApi.listMessages(sessionId)
    }
  }

  async function createSession(title: string, kbId: number | null = null): Promise<ChatSession> {
    const session = await chatApi.createSession(title, kbId)
    sessions.value.unshift(session)
    await selectSession(session.id)
    return session
  }

  async function deleteSession(sessionId: number) {
    await chatApi.deleteSession(sessionId)
    sessions.value = sessions.value.filter((s) => s.id !== sessionId)
    if (activeSessionId.value === sessionId) {
      await selectSession(null)
    }
  }

  /**
   * 更新会话（重命名/换 KB）
   * 本地列表同步替换，避免重拉
   */
  async function updateSession(
    sessionId: number,
    payload: { title?: string; kb_id?: number | null },
  ): Promise<ChatSession> {
    const updated = await chatApi.updateSession(sessionId, payload)
    const idx = sessions.value.findIndex((s) => s.id === sessionId)
    if (idx >= 0) {
      sessions.value[idx] = updated
    }
    return updated
  }

  /**
   * 发送消息并接收 Agent 完整回复
   * 乐观更新：先把用户消息显示出来，再等服务器返回
   */
  async function sendMessage(content: string): Promise<ChatResponse | null> {
    if (!activeSessionId.value || sending.value) return null
    sending.value = true

    // 乐观追加用户消息（id 暂用负数占位，后续 fetchMessages 替换）
    const optimisticUserMsg: ChatMessage = {
      id: -Date.now(),
      session_id: activeSessionId.value,
      role: 'user',
      content,
      agent_source: 'user',
      tool_calls_json: null,
      token_usage: null,
      created_at: new Date().toISOString(),
    }
    messages.value.push(optimisticUserMsg)

    try {
      const resp = await chatApi.sendMessage(activeSessionId.value, content)

      // 用真实数据替换 + 追加 assistant 回复
      // 简单做法：重新拉一遍消息列表
      messages.value = await chatApi.listMessages(activeSessionId.value)

      // 记录思考过程
      lastIntent.value = resp.intent
      lastRouteReason.value = resp.route_reason
      lastSkillUsed.value = resp.skill_used
      lastTrace.value = resp.execution_trace
      lastToolCalls.value = resp.tool_calls
      lastRetrievedDocs.value = resp.retrieved_docs

      // 会话标题可能被后端更新（首次发消息时）
      await fetchSessions()
      return resp
    } catch (e) {
      // 回滚乐观追加
      messages.value = messages.value.filter((m) => m.id !== optimisticUserMsg.id)
      throw e
    } finally {
      sending.value = false
    }
  }

  /**
   * 流式发送消息（SSE，打字机效果）
   * 乐观追加 user msg + 立刻插入空 assistant msg，chunks 实时往里 append
   */
  async function sendMessageStream(content: string): Promise<void> {
    if (!activeSessionId.value || sending.value) return
    sending.value = true
    clearTrace()

    // 乐观追加 user 消息
    const optimisticUserMsg: ChatMessage = {
      id: -Date.now(),
      session_id: activeSessionId.value,
      role: 'user',
      content,
      agent_source: 'user',
      tool_calls_json: null,
      token_usage: null,
      created_at: new Date().toISOString(),
    }
    messages.value.push(optimisticUserMsg)

    // 立刻插入一条占位的 assistant 消息（content 为空，由 chunks 填充）
    const placeholderAssistantId = -Date.now() - 1
    const assistantMsg: ChatMessage = {
      id: placeholderAssistantId,
      session_id: activeSessionId.value,
      role: 'assistant',
      content: '',
      agent_source: 'router',
      tool_calls_json: null,
      token_usage: null,
      created_at: new Date().toISOString(),
    }
    messages.value.push(assistantMsg)
    // 拿到 reactive 的引用（直接改 .content Vue 能追踪到）
    const assistantRef = messages.value[messages.value.length - 1]

    try {
      await chatApi.sendMessageStream(activeSessionId.value, content, {
        onStatus: () => {
          // 当前不展示阶段状态，但保留 hook 便于将来加 "Agent 正在思考..." 提示
        },
        onMeta: (data) => {
          // 提前更新思考过程的 Router 决策（chunks 还在流，思考面板已能看到判断）
          lastIntent.value = data.intent
          lastRouteReason.value = data.route_reason
          lastSkillUsed.value = data.skill_used
          // 同步 agent_source
          if (data.intent === 'rag') assistantRef.agent_source = 'rag'
          else if (data.intent === 'tool') assistantRef.agent_source = 'tool'
          else assistantRef.agent_source = 'router'
        },
        onChunk: (text) => {
          assistantRef.content += text
        },
        onDone: async (data) => {
          // 用真实数据替换占位 id + 元数据
          assistantRef.id = data.message_id
          assistantRef.tool_calls_json = data.tool_calls
          assistantRef.token_usage = data.token_usage || null
          // 思考过程完整快照
          lastTrace.value = data.execution_trace
          lastToolCalls.value = data.tool_calls
          lastRetrievedDocs.value = data.retrieved_docs
          // 会话标题可能变了（首条消息时）
          await fetchSessions()
        },
        onError: (data) => {
          // 把错误信息追加到 assistant 占位上
          assistantRef.content += `\n\n[错误] ${data.message}`
          throw new Error(data.message)
        },
      })
    } catch (e) {
      // 失败时移除占位 assistant；user msg 可以留着便于用户重发
      messages.value = messages.value.filter((m) => m.id !== placeholderAssistantId)
      throw e
    } finally {
      sending.value = false
    }
  }

  function clearTrace() {
    lastIntent.value = ''
    lastRouteReason.value = ''
    lastSkillUsed.value = null
    lastTrace.value = []
    lastToolCalls.value = []
    lastRetrievedDocs.value = []
  }

  return {
    sessions,
    sessionsLoading,
    activeSessionId,
    activeSession,
    messages,
    sending,
    lastIntent,
    lastRouteReason,
    lastSkillUsed,
    lastTrace,
    lastToolCalls,
    lastRetrievedDocs,
    fetchSessions,
    selectSession,
    createSession,
    updateSession,
    deleteSession,
    sendMessage,
    sendMessageStream,
    clearTrace,
  }
})
