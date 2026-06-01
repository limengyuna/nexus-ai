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

export interface ProfileSlotItem {
  slot_key: string
  slot_type: string
  slot_value: any
  confidence: number
  source: string
  updated_at: string
}

export interface MemoryCandidateItem {
  id: number
  user_id: number
  candidate_text: string
  suggested_slot_key: string | null
  suggested_value: any
  reason: string | null
  confidence: number
  seen_count: number
  status: string
  source_session_id: number | null
  source_message_id: number | null
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

/** 获取当前用户的结构化档案列表 */
export function listProfileValues(params?: { slotType?: string }): Promise<ProfileSlotItem[]> {
  const query: Record<string, string> = {}
  if (params?.slotType) query.slot_type = params.slotType
  return request.get('/memory/profile', { params: query }).then((res: any) => res.profile)
}

/** 手动更新档案槽位 */
export function updateProfileValue(slotKey: string, slotValue: any, source = 'manual'): Promise<ProfileSlotItem> {
  return request.put(`/memory/profile/${slotKey}`, { slot_value: slotValue, source })
}

/** 删除档案槽位 */
export function deleteProfileValue(slotKey: string): Promise<boolean> {
  return request.delete(`/memory/profile/${slotKey}`)
}

/** 获取待处理的候选偏好列表 */
export function listCandidates(): Promise<MemoryCandidateItem[]> {
  return request.get('/memory/profile/candidates').then((res: any) => res.candidates)
}

/** 采纳候选偏好 */
export function acceptCandidate(candidateId: number, slotValue?: any): Promise<ProfileSlotItem> {
  return request.post(`/memory/profile/candidates/${candidateId}/accept`, { slot_value: slotValue })
}

/** 拒绝候选偏好 */
export function rejectCandidate(candidateId: number): Promise<boolean> {
  return request.post(`/memory/profile/candidates/${candidateId}/reject`)
}

