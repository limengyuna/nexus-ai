/**
 * 知识库 + 文档 + 任务相关 API
 */
import request from './request'

// ---------- 类型 ----------
export type ChunkStrategy = 'recursive' | 'markdown' | 'semantic'
export type DocumentStatus = 'pending' | 'parsing' | 'cleaning' | 'chunking' | 'embedding' | 'storing' | 'completed' | 'failed'
export type TaskStatus = 'pending' | 'running' | 'success' | 'failed' | 'cancelled'

export interface KnowledgeBase {
  id: number
  name: string
  description: string | null
  chunk_strategy: ChunkStrategy
  chunk_size: number
  chunk_overlap: number
  enable_llm_clean: boolean
  collection_name: string | null
  created_by: number
  created_at: string
  updated_at: string
  document_count: number
}

export interface DocumentItem {
  id: number
  kb_id: number
  file_name: string
  file_type: string
  file_size: number
  chunk_count: number
  status: DocumentStatus
  // 文档级分块策略；为 null 表示沿用 KB 默认
  chunk_strategy: ChunkStrategy | null
  // 文档级 LLM 清洗开关；为 null 表示沿用 KB 默认
  enable_llm_clean: boolean | null
  error_msg: string | null
  created_at: string
  updated_at: string
}

export interface TaskRecord {
  id: number
  celery_task_id: string | null
  type: string
  status: TaskStatus
  detail_status?: DocumentStatus | null
  related_id: number | null
  progress: number
  error_msg: string | null
  created_at: string
  finished_at: string | null
}

export interface KnowledgeBaseCreate {
  name: string
  description?: string
  chunk_strategy?: ChunkStrategy
  chunk_size?: number
  chunk_overlap?: number
  enable_llm_clean?: boolean
}

export interface KnowledgeBaseUpdate {
  name?: string
  description?: string
  // 分块策略与大小理论上可改，但已上传的文档不会重新切；
  // 前端 UI 默认只暴露 name/description 修改
  chunk_strategy?: ChunkStrategy
  chunk_size?: number
  chunk_overlap?: number
  enable_llm_clean?: boolean
}

// ---------- 知识库 ----------
export function listKnowledgeBases(): Promise<KnowledgeBase[]> {
  return request.get('/knowledge-bases')
}

export function getKnowledgeBase(id: number): Promise<KnowledgeBase> {
  return request.get(`/knowledge-bases/${id}`)
}

export function createKnowledgeBase(payload: KnowledgeBaseCreate): Promise<KnowledgeBase> {
  return request.post('/knowledge-bases', payload)
}

export function updateKnowledgeBase(id: number, payload: KnowledgeBaseUpdate): Promise<KnowledgeBase> {
  return request.patch(`/knowledge-bases/${id}`, payload)
}

export function deleteKnowledgeBase(id: number): Promise<null> {
  return request.delete(`/knowledge-bases/${id}`)
}

// ---------- 文档 ----------
export interface ChunkPreview {
  chunk_id: string
  content: string
  metadata: Record<string, any>
}

export interface ChunksResponse {
  document_id: number
  file_name: string
  total: number
  chunks: ChunkPreview[]
}

export function listDocuments(kbId: number): Promise<DocumentItem[]> {
  return request.get(`/knowledge-bases/${kbId}/documents`)
}

export function listDocumentChunks(
  kbId: number,
  documentId: number,
  params?: { limit?: number; offset?: number; keyword?: string }
): Promise<ChunksResponse> {
  return request.get(`/knowledge-bases/${kbId}/documents/${documentId}/chunks`, { params })
}

export function reprocessDocument(kbId: number, documentId: number): Promise<TaskRecord> {
  return request.post(`/knowledge-bases/${kbId}/documents/${documentId}/reprocess`)
}

export interface UploadResult {
  document: DocumentItem
  task: TaskRecord
}

export function uploadDocument(
  kbId: number,
  file: File,
  chunkStrategy?: ChunkStrategy,
  enableLlmClean?: boolean,
): Promise<UploadResult> {
  const fd = new FormData()
  fd.append('file', file)
  // 可选：覆盖 KB 默认策略
  if (chunkStrategy) {
    fd.append('chunk_strategy', chunkStrategy)
  }
  // 可选：覆盖 KB 默认 LLM 清洗开关（显式 true / false 都会上传，undefined 才沿用 KB）
  if (enableLlmClean !== undefined) {
    fd.append('enable_llm_clean', String(enableLlmClean))
  }
  return request.post(`/knowledge-bases/${kbId}/documents`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function deleteDocument(kbId: number, docId: number): Promise<null> {
  return request.delete(`/knowledge-bases/${kbId}/documents/${docId}`)
}

// ---------- 任务进度 ----------
export function getTask(taskId: number): Promise<TaskRecord> {
  return request.get(`/tasks/${taskId}`)
}
