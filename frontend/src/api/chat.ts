/**
 * 对话相关 API
 */
import request from './request'

// ---------- 类型 ----------
export type MessageRole = 'user' | 'assistant' | 'system'
export type AgentSource = 'user' | 'router' | 'rag' | 'tool' | 'summary'

export interface ChatSession {
  id: number
  title: string
  user_id: number
  kb_id: number | null
  summary: string | null
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  session_id: number
  role: MessageRole
  content: string
  agent_source: AgentSource | null
  tool_calls_json: any
  token_usage: number | null
  is_archived?: boolean
  created_at: string
}

export interface TraceStep {
  node: string
  started_at: number
  elapsed_ms: number
  input: Record<string, any>
  output: Record<string, any>
  error: string | null
}

export interface RetrievedDoc {
  chunk_id: string
  content: string
  score: number
  metadata: Record<string, any>
  adopted?: boolean  // 是否通过软过滤被 LLM 实际采用
}

export interface ToolCall {
  name: string
  kind: string
  arguments: Record<string, any>
  result: any
  step?: number  // 归属的执行计划步骤编号
}

export interface RetrievedMemory {
  id: number
  content: string
  fact_type: string
  importance: number
}

export interface FaithfulnessClaim {
  text: string           // 从回答中提取的事实声明
  supported: boolean     // 是否有资料支撑
  source_index: number   // 支撑该声明的资料编号（0 表示无来源）
  reason: string         // 判断理由
}

export interface FaithfulnessResult {
  score: number              // 忠实度评分（0.0 ~ 1.0，-1 表示校验失败）
  claims: FaithfulnessClaim[]
  total_claims: number
  supported_claims: number
  elapsed_ms: number
}

export interface ChatResponse {
  message: ChatMessage
  intent: string
  route_reason: string
  skill_used: string | null
  tool_calls: ToolCall[]
  retrieved_docs: RetrievedDoc[]
  retrieved_memories: RetrievedMemory[]
  execution_trace: TraceStep[]
}

// ---------- API ----------
export function createSession(title: string, kbId: number | null = null): Promise<ChatSession> {
  return request.post('/chat/sessions', { title, kb_id: kbId })
}

export function listSessions(): Promise<ChatSession[]> {
  return request.get('/chat/sessions')
}

export function listMessages(sessionId: number): Promise<ChatMessage[]> {
  return request.get(`/chat/sessions/${sessionId}/messages`)
}

export function deleteSession(sessionId: number): Promise<null> {
  return request.delete(`/chat/sessions/${sessionId}`)
}

export interface ChatSessionUpdate {
  title?: string
  kb_id?: number | null
}

export function updateSession(sessionId: number, payload: ChatSessionUpdate): Promise<ChatSession> {
  return request.patch(`/chat/sessions/${sessionId}`, payload)
}

export function sendMessage(sessionId: number, message: string): Promise<ChatResponse> {
  return request.post(`/chat/sessions/${sessionId}/messages`, { message })
}

/**
 * 主动取消正在执行的 Agent 任务（协作式中断）
 * - 后端只是写一个内存标记，立刻返回；真正"停下来"靠 graph 节点轮询此标记
 * - 通常前端会同时执行：① AbortController.abort() 关 SSE 流；② 调用此函数
 *   两者配合：① 让 UI 立刻不再追加 chunk；② 让后端 graph 真正停止跑
 */
export function cancelMessage(sessionId: number): Promise<{ session_id: number; cancelled: boolean }> {
  return request.post(`/chat/sessions/${sessionId}/cancel`)
}

// ---------- SSE 流式 ----------
/** 工具审批请求载荷（type='tool_approval'） */
export interface ApprovalPayload {
  type: 'tool_approval'
  tool_name: string
  tool_kind: 'internal' | 'mcp' | 'skill'
  description: string
  arguments: Record<string, any>
  message: string
}

/** 用户主动中断载荷（type='cancelled'，由 supervisor 在 interrupt() 时构造） */
export interface CancelledPayload {
  type: 'cancelled'
  task_plan: any[]
  intent: string
  route_reason: string
  message: string
}

/** interrupt 事件统一载荷 —— 通过 payload.type 区分子类 */
export type InterruptPayload = ApprovalPayload | CancelledPayload

export interface InterruptEvent {
  user_msg_id: number       // resume 时必传，定位 thread_id
  session_id: number
  payload: InterruptPayload
}

/** resume 决策：approve/reject 用于工具审批；continue 用于用户主动中断的续跑 */
export interface ResumeDecision {
  user_msg_id: number
  action: 'approve' | 'reject' | 'continue'
  reason?: string
  edited_args?: Record<string, any> | null
}

export interface StreamHandlers {
  onStatus?: (data: { step: string; user_msg_id?: number }) => void
  onMeta?: (data: { intent: string; route_reason: string; skill_used: string | null; task_plan?: any[] }) => void
  onChunk?: (text: string) => void
  onApprovalPending?: (data: ApprovalPayload) => void  // tool_agent 即将 interrupt 的提示（可选体验事件）
  onInterrupt?: (data: InterruptEvent) => void         // 真正的中断事件，需要用户审批后调用 resumeMessageStream
  onDone?: (data: {
    message_id: number
    session_id: number
    tool_calls: ToolCall[]
    execution_trace: TraceStep[]
    retrieved_docs: RetrievedDoc[]
    retrieved_memories: RetrievedMemory[]
    task_plan: any[]
    faithfulness: FaithfulnessResult | null
    token_usage: number
    agent_source: string
    resumed?: boolean       // 是否由 resume 端点产生
  }) => void
  onError?: (data: { message: string; type: string }) => void
}

/**
 * 流式发送消息（SSE）
 * 用 fetch + ReadableStream 接收（比 EventSource 灵活，可以带 Authorization header）
 */
export async function sendMessageStream(
  sessionId: number,
  message: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await openSseStream(
    `/api/v1/chat/sessions/${sessionId}/messages/stream`,
    { message },
    handlers,
    signal,
  )
}

/**
 * 中断恢复（SSE）—— 用户对工具审批后调用，传 approve/reject 决定
 * 后端从 checkpoint 恢复执行，继续推送 token；可能再次产生 interrupt 事件（多次审批）
 */
export async function resumeMessageStream(
  sessionId: number,
  decision: ResumeDecision,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  await openSseStream(
    `/api/v1/chat/sessions/${sessionId}/resume`,
    decision,
    handlers,
    signal,
  )
}

// 抽取的共用 SSE 读取逻辑：发起 POST，逐帧解析 \n\n 分隔的事件
async function openSseStream(
  url: string,
  body: any,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = localStorage.getItem('access_token')
  if (!token) throw new Error('未登录')

  const resp = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
    signal,
  })

  if (!resp.ok || !resp.body) {
    const err = await resp.text().catch(() => '请求失败')
    throw new Error(`SSE 请求失败 (${resp.status}): ${err}`)
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sepIdx: number
    while ((sepIdx = buffer.indexOf('\n\n')) >= 0) {
      const rawEvent = buffer.slice(0, sepIdx)
      buffer = buffer.slice(sepIdx + 2)
      parseAndDispatch(rawEvent, handlers)
    }
  }
  if (buffer.trim()) parseAndDispatch(buffer, handlers)
}

function parseAndDispatch(rawEvent: string, handlers: StreamHandlers) {
  let eventType = 'message'
  let dataLine = ''
  for (const line of rawEvent.split('\n')) {
    if (line.startsWith('event:')) eventType = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLine += line.slice(5).trim()
  }
  if (!dataLine) return
  let data: any
  try {
    data = JSON.parse(dataLine)
  } catch {
    return
  }
  switch (eventType) {
    case 'status': handlers.onStatus?.(data); break
    case 'meta': handlers.onMeta?.(data); break
    case 'chunk': handlers.onChunk?.(data.text ?? ''); break
    case 'approval_pending': handlers.onApprovalPending?.(data); break
    case 'interrupt': handlers.onInterrupt?.(data); break
    case 'done': handlers.onDone?.(data); break
    case 'error': handlers.onError?.(data); break
  }
}
