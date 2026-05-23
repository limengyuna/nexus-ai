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
  FaithfulnessResult,
  RetrievedDoc,
  RetrievedMemory,
  ToolCall,
  TraceStep,
} from '@/api/chat'
import * as chatApi from '@/api/chat'

// ---------- LocalStorage 思考过程持久化辅助函数 ----------
// Supervisor 决策历史项（每一轮 dispatch 的快照）
interface DecisionEntry {
  intent: string
  routeReason: string
  timestamp: number
}

function saveThinkingTrace(
  sessionId: number,
  messageId: number,
  data: {
    intent: string
    route_reason: string
    skill_used: string | null
    execution_trace: TraceStep[]
    tool_calls: ToolCall[]
    retrieved_docs: RetrievedDoc[]
    retrieved_memories?: RetrievedMemory[]
    task_plan?: any[] // 新增执行计划字段
    decisions?: DecisionEntry[] // 新增决策历史字段
    faithfulness?: FaithfulnessResult | null // 忠实性校验结果
  }
) {
  try {
    const raw = localStorage.getItem('nexus_thinking_traces')
    let tracesStore: any[] = raw ? JSON.parse(raw) : []

    // 找到当前会话的存储记录
    let conv = tracesStore.find((item) => item.sessionId === sessionId)
    if (!conv) {
      conv = {
        sessionId,
        lastUpdated: Date.now(),
        snapshots: []
      }
      tracesStore.push(conv)
    }

    // 构造当前消息的思考过程快照
    const snapshot = {
      messageId,
      intent: data.intent,
      routeReason: data.route_reason,
      skillUsed: data.skill_used,
      trace: data.execution_trace,
      toolCalls: data.tool_calls,
      retrievedDocs: data.retrieved_docs,
      retrievedMemories: data.retrieved_memories || [],
      taskPlan: data.task_plan || [], // 新增持久化存储执行计划
      decisions: data.decisions || [], // 新增持久化存储决策历史
      faithfulness: data.faithfulness || null, // 忠实性校验结果
      timestamp: Date.now()
    }

    // 去重：如果同一个 messageId 已经有了，先删掉旧的
    conv.snapshots = conv.snapshots.filter((s: any) => s.messageId !== messageId)
    // 头部追加最新的快照
    conv.snapshots.unshift(snapshot)
    // 每个会话最多保存最新的 3 个思考过程
    if (conv.snapshots.length > 3) {
      conv.snapshots = conv.snapshots.slice(0, 3)
    }

    // 更新最后活跃时间
    conv.lastUpdated = Date.now()

    // 将本会话移动到最前（作为最新活跃会话）
    tracesStore = tracesStore.filter((item) => item.sessionId !== sessionId)
    tracesStore.unshift(conv)

    // 保证总共只保留最新活跃的 3 个会话的思考过程，多余的彻底淘汰（LRU淘汰策略）
    if (tracesStore.length > 3) {
      tracesStore = tracesStore.slice(0, 3)
    }

    localStorage.setItem('nexus_thinking_traces', JSON.stringify(tracesStore))
  } catch (err) {
    console.error('Failed to save thinking trace to localStorage:', err)
  }
}

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
  const lastTaskPlan = ref<any[]>([])  // Supervisor 动态任务计划
  const lastDecisions = ref<DecisionEntry[]>([])  // Supervisor 决策历史（按时间顺序）
  const lastTrace = ref<TraceStep[]>([])
  const lastToolCalls = ref<ToolCall[]>([])
  const lastRetrievedDocs = ref<RetrievedDoc[]>([])
  const lastRetrievedMemories = ref<RetrievedMemory[]>([])
  const lastFaithfulness = ref<FaithfulnessResult | null>(null)
  const activeThinkingMessageId = ref<number | null>(null)

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

  function loadThinkingTrace(sessionId: number) {
    try {
      const raw = localStorage.getItem('nexus_thinking_traces')
      if (!raw) {
        clearTrace()
        return
      }
      const tracesStore = JSON.parse(raw)
      const conv = tracesStore.find((item: any) => item.sessionId === sessionId)
      if (conv && conv.snapshots && conv.snapshots.length > 0) {
        const snapshot = conv.snapshots[0]
        lastIntent.value = snapshot.intent
        lastRouteReason.value = snapshot.routeReason
        lastSkillUsed.value = snapshot.skillUsed
        lastTrace.value = snapshot.trace || []
        lastToolCalls.value = snapshot.toolCalls || []
        lastRetrievedDocs.value = snapshot.retrievedDocs || []
        lastRetrievedMemories.value = snapshot.retrievedMemories || []
        lastFaithfulness.value = snapshot.faithfulness || null
        lastTaskPlan.value = snapshot.taskPlan || [] // 恢复加载本地存储的执行计划
        lastDecisions.value = snapshot.decisions || [] // 恢复决策历史
        activeThinkingMessageId.value = snapshot.messageId
      } else {
        clearTrace()
      }
    } catch (err) {
      console.error('Failed to load thinking trace from localStorage:', err)
      clearTrace()
    }
  }

  function loadThinkingTraceForMessage(sessionId: number, messageId: number) {
    try {
      const raw = localStorage.getItem('nexus_thinking_traces')
      if (!raw) return
      const tracesStore = JSON.parse(raw)
      const conv = tracesStore.find((item: any) => item.sessionId === sessionId)
      if (conv && conv.snapshots) {
        const snapshot = conv.snapshots.find((s: any) => s.messageId === messageId)
        if (snapshot) {
          lastIntent.value = snapshot.intent
          lastRouteReason.value = snapshot.routeReason
          lastSkillUsed.value = snapshot.skillUsed
          lastTrace.value = snapshot.trace || []
          lastToolCalls.value = snapshot.toolCalls || []
          lastRetrievedDocs.value = snapshot.retrievedDocs || []
          lastRetrievedMemories.value = snapshot.retrievedMemories || []
          lastFaithfulness.value = snapshot.faithfulness || null
          lastTaskPlan.value = snapshot.taskPlan || [] // 切换消息时，恢复加载对应执行计划
          lastDecisions.value = snapshot.decisions || [] // 恢复决策历史
          activeThinkingMessageId.value = snapshot.messageId
        }
      }
    } catch (err) {
      console.error('Failed to load snapshot for message:', err)
    }
  }

  async function selectSession(sessionId: number | null) {
    activeSessionId.value = sessionId
    messages.value = []
    clearTrace()
    if (sessionId !== null) {
      messages.value = await chatApi.listMessages(sessionId)
      loadThinkingTrace(sessionId)
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
    
    // 清理 localStorage 中的会话数据
    try {
      const raw = localStorage.getItem('nexus_thinking_traces')
      if (raw) {
        let tracesStore = JSON.parse(raw)
        tracesStore = tracesStore.filter((item: any) => item.sessionId !== sessionId)
        localStorage.setItem('nexus_thinking_traces', JSON.stringify(tracesStore))
      }
    } catch {}

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
      lastRetrievedMemories.value = resp.retrieved_memories || []
      // 非流式只能拿到最终一次决策，构造单元素历史列表
      lastDecisions.value = resp.intent && resp.route_reason
        ? [{ intent: resp.intent, routeReason: resp.route_reason, timestamp: Date.now() }]
        : []

      // 保存最新思考快照到 LocalStorage
      const assistantMsg = messages.value.find((m) => m.role === 'assistant' && m.id > 0)
      const messageId = assistantMsg ? assistantMsg.id : Date.now()
      saveThinkingTrace(activeSessionId.value, messageId, {
        intent: resp.intent,
        route_reason: resp.route_reason,
        skill_used: resp.skill_used,
        execution_trace: resp.execution_trace,
        tool_calls: resp.tool_calls,
        retrieved_docs: resp.retrieved_docs,
        retrieved_memories: resp.retrieved_memories,
        decisions: lastDecisions.value, // 持久化决策历史
      })

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
        onMeta: (data: any) => {
          // 提前更新思考过程（chunks 还在流，思考面板已能看到判断）
          lastIntent.value = data.intent
          lastRouteReason.value = data.route_reason
          lastSkillUsed.value = data.skill_used
          // 接收 Supervisor 的任务计划
          if (data.task_plan) {
            lastTaskPlan.value = data.task_plan
          }
          // 追加 Supervisor 决策到历史列表（带去重：与最近一条相同的 intent+reason 不重复记录）
          if (data.intent && data.route_reason) {
            const last = lastDecisions.value[lastDecisions.value.length - 1]
            if (!last || last.intent !== data.intent || last.routeReason !== data.route_reason) {
              lastDecisions.value = [
                ...lastDecisions.value,
                { intent: data.intent, routeReason: data.route_reason, timestamp: Date.now() },
              ]
            }
          }
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
          lastRetrievedMemories.value = data.retrieved_memories || []
          lastFaithfulness.value = data.faithfulness || null
          // 更新 task_plan 为最终完整状态
          if (data.task_plan && data.task_plan.length > 0) {
            lastTaskPlan.value = data.task_plan
          }

          // 保存思考过程到 LocalStorage
          if (activeSessionId.value) {
            saveThinkingTrace(activeSessionId.value, data.message_id, {
              intent: lastIntent.value,
              route_reason: lastRouteReason.value,
              skill_used: lastSkillUsed.value,
              execution_trace: data.execution_trace,
              tool_calls: data.tool_calls,
              retrieved_docs: data.retrieved_docs,
              retrieved_memories: data.retrieved_memories,
              task_plan: lastTaskPlan.value, // 完美传入最新执行计划
              decisions: lastDecisions.value, // 持久化决策历史
              faithfulness: lastFaithfulness.value, // 忠实性校验结果
            })
          }

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
    lastTaskPlan.value = []
    lastDecisions.value = []
    lastTrace.value = []
    lastToolCalls.value = []
    lastRetrievedDocs.value = []
    lastRetrievedMemories.value = []
    lastFaithfulness.value = null
    activeThinkingMessageId.value = null
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
    lastTaskPlan,
    lastDecisions,
    lastTrace,
    lastToolCalls,
    lastRetrievedDocs,
    lastRetrievedMemories,
    lastFaithfulness,
    activeThinkingMessageId,
    fetchSessions,
    selectSession,
    createSession,
    updateSession,
    deleteSession,
    sendMessage,
    sendMessageStream,
    clearTrace,
    loadThinkingTraceForMessage,
  }
})
