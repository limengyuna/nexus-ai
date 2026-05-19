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
}

export interface ChatResponse {
  message: ChatMessage
  intent: string
  route_reason: string
  skill_used: string | null
  tool_calls: ToolCall[]
  retrieved_docs: RetrievedDoc[]
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

// ---------- SSE 流式 ----------
export interface StreamHandlers {
  onStatus?: (data: { step: string; user_msg_id?: number }) => void
  onMeta?: (data: { intent: string; route_reason: string; skill_used: string | null }) => void
  onChunk?: (text: string) => void
  onDone?: (data: {
    message_id: number
    session_id: number
    tool_calls: ToolCall[]
    execution_trace: TraceStep[]
    retrieved_docs: RetrievedDoc[]
    token_usage: number
    agent_source: string
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
  // 与 request.ts / auth store 保持一致：localStorage key = 'access_token'
  const token = localStorage.getItem('access_token')
  if (!token) throw new Error('未登录')

  const resp = await fetch(`/api/v1/chat/sessions/${sessionId}/messages/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ message }),
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

    // SSE 帧以 \n\n 分隔
    let sepIdx: number
    while ((sepIdx = buffer.indexOf('\n\n')) >= 0) {
      const rawEvent = buffer.slice(0, sepIdx)
      buffer = buffer.slice(sepIdx + 2)
      parseAndDispatch(rawEvent, handlers)
    }
  }

  // flush 残余
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
    case 'done': handlers.onDone?.(data); break
    case 'error': handlers.onError?.(data); break
  }
}
