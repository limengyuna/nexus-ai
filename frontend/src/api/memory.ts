/**
 * L2 记忆管理 API
 */
import request from './request'

// ---------- 类型 ----------
export interface MemoryFact {
  id: number
  user_id: number
  session_id: number | null
  kb_id: number | null
  fact_type: string
  content: string
  importance: number
  access_count: number
  last_accessed_at: string | null
  created_at: string
  updated_at: string
}

// ---------- API ----------

/** 获取当前用户的所有记忆事实（可按类型、知识库过滤） */
export function listFacts(params?: {
  factType?: string
  kbId?: number
  scope?: 'global' | 'kb'
}): Promise<MemoryFact[]> {
  const query: Record<string, string | number> = {}
  if (params?.factType) query.fact_type = params.factType
  if (params?.kbId !== undefined) query.kb_id = params.kbId
  if (params?.scope) query.scope = params.scope
  return request.get('/memory/facts', { params: query })
}

/** 删除指定 ID 的记忆事实 */
export function deleteFact(factId: number): Promise<boolean> {
  return request.delete(`/memory/facts/${factId}`)
}
