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
  InterruptEvent,
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

  // 当前正在进行的 SSE 流的 AbortController，用于主动中断
  // sendMessageStream / resumeApproval 启动时新建，结束时置 null
  // stopGenerating action 通过它来 abort fetch + 调后端 cancel 接口
  const currentAbortController = ref<AbortController | null>(null)

  // 工具审批状态（当 Agent 调用危险工具触发 interrupt 时填充）
  const pendingApproval = ref<InterruptEvent | null>(null)

  // 被用户主动中断的 user_msg_id（用于显示"继续"按钮 + 调 resume 续跑）
  // 仅活在前端内存：刷新页面 / 切换会话即消失（与 Cursor、Windsurf 体验一致）
  // 用户发新消息时由 sendMessageStream 入口清空
  const interruptedUserMsgId = ref<number | null>(null)

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
    interruptedUserMsgId.value = null  // 切会话清掉"被中断"标记（与 Cursor 体验一致）
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
    // 用户发新消息时放弃老的"被中断 thread"——与 Cursor / Windsurf 行为一致
    // 老的 checkpoint 在 PostgresSaver 里依然存在，但前端不再显示"继续"按钮
    interruptedUserMsgId.value = null

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

    // 创建 AbortController，传给 SSE fetch；同时挂到 store 让 stopGenerating 能拿到
    const controller = new AbortController()
    currentAbortController.value = controller

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
        onInterrupt: (data) => {
          // [TEMP DEBUG] 排查"黄色卡片错乱"问题：看真实 payload 类型
          console.log('[DEBUG onInterrupt] payload.type =', data?.payload?.type, ' | full payload:', data?.payload)
          // 按 payload.type 区分两种中断：tool_approval（工具审批）vs cancelled（用户主动中断）
          if (data.payload?.type === 'cancelled') {
            // ---------- 用户主动中断的 cancelled-interrupt ----------
            // 后端 supervisor 已让 graph 暂停在 checkpoint，可通过 /resume action=continue 续跑
            interruptedUserMsgId.value = data.user_msg_id
            // 同步 task_plan（已完成的步骤会显示为 done，未完成的为 pending）
            const cancelPayload = data.payload as any
            if (cancelPayload?.task_plan) {
              lastTaskPlan.value = cancelPayload.task_plan
            }
            // 在 assistant 消息尾部追加提示
            if (assistantRef && assistantRef.role === 'assistant') {
              if (!assistantRef.content) assistantRef.content = '⏸ 已暂停（点击下方"继续"恢复执行）'
              else if (!assistantRef.content.includes('已暂停')) {
                assistantRef.content += '\n\n⏸ 已暂停（点击下方"继续"恢复执行）'
              }
            }
          } else {
            // ---------- 工具审批的 tool_approval-interrupt ----------
            pendingApproval.value = data
            assistantRef.content += '\n\n⚠️ Agent 想要调用一个工具，请在下方审批…'
          }
        },
        onError: (data) => {
          // 把错误信息追加到 assistant 占位上
          assistantRef.content += `\n\n[错误] ${data.message}`
          throw new Error(data.message)
        },
      }, controller.signal)
    } catch (e: any) {
      // AbortError 是用户主动中断，不当作错误
      const isAbort = e?.name === 'AbortError' || /aborted|abort/i.test(String(e?.message || ''))
      if (isAbort) {
        // 在 assistant 占位末尾打一个"已中断"小标记
        if (assistantRef && assistantRef.role === 'assistant') {
          if (!assistantRef.content) assistantRef.content = '[已中断]'
          else if (!assistantRef.content.endsWith('[已中断]')) assistantRef.content += '\n\n[已中断]'
        }
      } else {
        // 真正失败：移除占位 assistant；user msg 可以留着便于用户重发
        messages.value = messages.value.filter((m) => m.id !== placeholderAssistantId)
        throw e
      }
    } finally {
      sending.value = false
      currentAbortController.value = null
    }
  }

  /**
   * 主动停止当前正在进行的 Agent 任务（协作式中断 + 真断点续传）
   *
   * 关键设计：**不 abort fetch**，仅调后端 /cancel
   * - 后端 supervisor 检测到 cancel 标记后调 interrupt() 让 graph 暂停
   * - 暂停时会通过 SSE 推送 'interrupt' 事件（payload.type='cancelled'）
   * - 前端必须保持 SSE 流通畅才能收到这个事件，进而显示"继续"按钮
   * - 如果这里直接 abort 了 fetch，前端就收不到 interrupt 事件，无法续跑
   *
   * 兜底：90s 超时强制 abort（避免后端真挂死时 UI 永远转圈）
   */
  async function stopGenerating(): Promise<void> {
    if (!sending.value) return
    const sid = activeSessionId.value
    if (sid == null) return
    // 调后端 /cancel —— 后端只是写一个 flag，立刻返回
    chatApi.cancelMessage(sid).catch((e) => {
      console.warn('[chat] cancelMessage failed:', e)
    })
    // 兜底：90 秒后若 sending 仍为 true（后端没正常推 interrupt），强制 abort
    const controllerSnapshot = currentAbortController.value
    setTimeout(() => {
      if (sending.value && currentAbortController.value === controllerSnapshot) {
        console.warn('[chat] cancel 90s 超时未响应，强制 abort fetch')
        controllerSnapshot?.abort()
      }
    }, 90_000)
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

  /**
   * 用户对危险工具调用审批后，恢复图执行
   * @param action 'approve' | 'reject'
   * @param reason 拒绝理由（可选）
   * @param editedArgs 用户编辑后的参数（可选、仅 approve 时可用）
   */
  async function resumeApproval(
    action: 'approve' | 'reject',
    reason?: string,
    editedArgs?: Record<string, any> | null,
  ): Promise<void> {
    const approval = pendingApproval.value
    if (!approval || !activeSessionId.value) return
    pendingApproval.value = null  // 清除审批状态
    sending.value = true

    // 找到当前占位的 assistant 消息，继续往里填充
    const assistantRef = messages.value[messages.value.length - 1]

    // 清除之前的审批提示文本
    if (assistantRef && assistantRef.role === 'assistant') {
      assistantRef.content = assistantRef.content.replace(
        /\n\n⚠️ Agent 想要调用一个工具，请在下方审批…$/,
        '',
      )
    }

    try {
      await chatApi.resumeMessageStream(activeSessionId.value, {
        user_msg_id: approval.user_msg_id,
        action,
        reason,
        edited_args: editedArgs,
      }, {
        onStatus: () => {},
        onMeta: (data: any) => {
          lastIntent.value = data.intent
          lastRouteReason.value = data.route_reason
          lastSkillUsed.value = data.skill_used
          if (data.task_plan) lastTaskPlan.value = data.task_plan
        },
        onChunk: (text) => {
          if (assistantRef && assistantRef.role === 'assistant') {
            assistantRef.content += text
          }
        },
        onInterrupt: (data) => {
          // 再次中断（多次审批场景）
          pendingApproval.value = data
          if (assistantRef && assistantRef.role === 'assistant') {
            assistantRef.content += '\n\n⚠️ Agent 想要调用一个工具，请在下方审批…'
          }
        },
        onDone: async (data) => {
          if (assistantRef && assistantRef.role === 'assistant') {
            assistantRef.id = data.message_id
            assistantRef.tool_calls_json = data.tool_calls
            assistantRef.token_usage = data.token_usage || null
          }
          lastTrace.value = data.execution_trace
          lastToolCalls.value = data.tool_calls
          lastRetrievedDocs.value = data.retrieved_docs
          lastRetrievedMemories.value = data.retrieved_memories || []
          lastFaithfulness.value = data.faithfulness || null
          if (data.task_plan?.length) lastTaskPlan.value = data.task_plan
          if (activeSessionId.value) {
            saveThinkingTrace(activeSessionId.value, data.message_id, {
              intent: lastIntent.value,
              route_reason: lastRouteReason.value,
              skill_used: lastSkillUsed.value,
              execution_trace: data.execution_trace,
              tool_calls: data.tool_calls,
              retrieved_docs: data.retrieved_docs,
              retrieved_memories: data.retrieved_memories,
              task_plan: lastTaskPlan.value,
              decisions: lastDecisions.value,
              faithfulness: lastFaithfulness.value,
            })
          }
          await fetchSessions()
        },
        onError: (data) => {
          if (assistantRef && assistantRef.role === 'assistant') {
            assistantRef.content += `\n\n[恢复失败] ${data.message}`
          }
        },
      })
    } finally {
      sending.value = false
    }
  }

  /**
   * 从用户主动中断的位置续跑（不会重做已完成的步骤）
   *
   * 工作机制：
   * - supervisor 中断时调用了 interrupt({type:"cancelled"})，graph 状态保存在 PostgresSaver
   * - 此处用 Command(resume={action:"continue"}) 从 checkpoint 续跑
   * - supervisor 重跑入口时 cancel flag 已清，interrupt() 直接返回 decision，节点正常往下走
   * - 因为 task_plan 中已完成的 step 状态保留，supervisor 会直接派发下一个 pending 的 step
   *
   * 与 resumeApproval 区别：
   * - resumeApproval 用于工具审批（approve/reject）
   * - continueInterrupted 用于用户主动中断后的续跑（continue）
   * 两者后端共享同一个 /resume 端点，仅 decision.action 不同
   */
  async function continueInterrupted(): Promise<void> {
    const userMsgId = interruptedUserMsgId.value
    if (userMsgId == null || !activeSessionId.value || sending.value) return
    interruptedUserMsgId.value = null
    sending.value = true

    // 找到当前占位的 assistant 消息（最后一条），继续往里填充
    const assistantRef = messages.value[messages.value.length - 1]
    // 清除"已暂停"提示文案，恢复时重新追加
    if (assistantRef && assistantRef.role === 'assistant') {
      assistantRef.content = assistantRef.content.replace(/\n*⏸ 已暂停（点击下方"继续"恢复执行）$/, '')
    }

    // 创建新的 AbortController（resume 也是一次 SSE 流，可被再次 stop）
    const controller = new AbortController()
    currentAbortController.value = controller

    try {
      await chatApi.resumeMessageStream(activeSessionId.value, {
        user_msg_id: userMsgId,
        action: 'continue',
      }, {
        onStatus: () => {},
        onMeta: (data: any) => {
          lastIntent.value = data.intent
          lastRouteReason.value = data.route_reason
          lastSkillUsed.value = data.skill_used
          if (data.task_plan) lastTaskPlan.value = data.task_plan
        },
        onChunk: (text) => {
          if (assistantRef && assistantRef.role === 'assistant') {
            assistantRef.content += text
          }
        },
        onInterrupt: (data) => {
          // 续跑过程中又被中断（再次点了停止 / 工具审批）
          if (data.payload?.type === 'cancelled') {
            interruptedUserMsgId.value = data.user_msg_id
            const cp = data.payload as any
            if (cp?.task_plan) lastTaskPlan.value = cp.task_plan
            if (assistantRef && assistantRef.role === 'assistant'
                && !assistantRef.content.includes('已暂停')) {
              assistantRef.content += '\n\n⏸ 已暂停（点击下方"继续"恢复执行）'
            }
          } else {
            pendingApproval.value = data
            if (assistantRef && assistantRef.role === 'assistant') {
              assistantRef.content += '\n\n⚠️ Agent 想要调用一个工具，请在下方审批…'
            }
          }
        },
        onDone: async (data) => {
          if (assistantRef && assistantRef.role === 'assistant') {
            assistantRef.id = data.message_id
            assistantRef.tool_calls_json = data.tool_calls
            assistantRef.token_usage = data.token_usage || null
          }
          lastTrace.value = data.execution_trace
          lastToolCalls.value = data.tool_calls
          lastRetrievedDocs.value = data.retrieved_docs
          lastRetrievedMemories.value = data.retrieved_memories || []
          lastFaithfulness.value = data.faithfulness || null
          if (data.task_plan?.length) lastTaskPlan.value = data.task_plan
          if (activeSessionId.value) {
            saveThinkingTrace(activeSessionId.value, data.message_id, {
              intent: lastIntent.value,
              route_reason: lastRouteReason.value,
              skill_used: lastSkillUsed.value,
              execution_trace: data.execution_trace,
              tool_calls: data.tool_calls,
              retrieved_docs: data.retrieved_docs,
              retrieved_memories: data.retrieved_memories,
              task_plan: lastTaskPlan.value,
              decisions: lastDecisions.value,
              faithfulness: lastFaithfulness.value,
            })
          }
          await fetchSessions()
        },
        onError: (data) => {
          if (assistantRef && assistantRef.role === 'assistant') {
            assistantRef.content += `\n\n[续跑失败] ${data.message}`
          }
        },
      }, controller.signal)
    } catch (e: any) {
      const isAbort = e?.name === 'AbortError' || /aborted|abort/i.test(String(e?.message || ''))
      if (!isAbort) {
        if (assistantRef && assistantRef.role === 'assistant') {
          assistantRef.content += `\n\n[续跑出错] ${String(e?.message || e)}`
        }
      }
    } finally {
      sending.value = false
      currentAbortController.value = null
    }
  }

  return {
    sessions,
    sessionsLoading,
    activeSessionId,
    activeSession,
    messages,
    sending,
    pendingApproval,
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
    stopGenerating,
    resumeApproval,
    interruptedUserMsgId,
    continueInterrupted,
    clearTrace,
    loadThinkingTraceForMessage,
  }
})
