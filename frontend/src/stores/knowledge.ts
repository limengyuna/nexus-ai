/**
 * 知识库 + 文档状态管理
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as kbApi from '@/api/knowledge'
import type { ChunkStrategy, DocumentItem, KnowledgeBase, KnowledgeBaseCreate, KnowledgeBaseUpdate, TaskRecord } from '@/api/knowledge'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const documents = ref<DocumentItem[]>([])
  const loading = ref(false)

  async function fetchKnowledgeBases() {
    loading.value = true
    try {
      knowledgeBases.value = await kbApi.listKnowledgeBases()
    } finally {
      loading.value = false
    }
  }

  async function createKnowledgeBase(payload: KnowledgeBaseCreate): Promise<KnowledgeBase> {
    const kb = await kbApi.createKnowledgeBase(payload)
    knowledgeBases.value.unshift(kb)
    return kb
  }

  async function updateKnowledgeBase(id: number, payload: KnowledgeBaseUpdate): Promise<KnowledgeBase> {
    const updated = await kbApi.updateKnowledgeBase(id, payload)
    // 替换列表中对应项
    const idx = knowledgeBases.value.findIndex((k) => k.id === id)
    if (idx >= 0) {
      knowledgeBases.value[idx] = updated
    }
    return updated
  }

  async function deleteKnowledgeBase(id: number) {
    await kbApi.deleteKnowledgeBase(id)
    knowledgeBases.value = knowledgeBases.value.filter((k) => k.id !== id)
  }

  async function fetchDocuments(kbId: number) {
    documents.value = await kbApi.listDocuments(kbId)
  }

  async function uploadDocument(
    kbId: number,
    file: File,
    onProgress?: (task: TaskRecord) => void,
    chunkStrategy?: ChunkStrategy,
    enableLlmClean?: boolean,
  ) {
    const { task } = await kbApi.uploadDocument(kbId, file, chunkStrategy, enableLlmClean)
    // 轮询任务进度
    return pollTask(task.id, onProgress)
  }

  async function pollTask(
    taskId: number,
    onProgress?: (task: TaskRecord) => void,
  ): Promise<TaskRecord> {
    // 轮询配置：每 2 秒拉一次，最多 30 分钟。
    // 长耗时场景（如启用 LLM 清洗的大文档）总时长可达 10+ 分钟。
    const POLL_INTERVAL_MS = 2000
    const MAX_DURATION_MS = 30 * 60 * 1000 // 30 分钟
    const MAX_ATTEMPTS = Math.ceil(MAX_DURATION_MS / POLL_INTERVAL_MS)

    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      const t = await kbApi.getTask(taskId)
      onProgress?.(t)
      if (t.status === 'success' || t.status === 'failed' || t.status === 'cancelled') {
        return t
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
    }
    throw new Error('任务超时（已超过 30 分钟，请到后台查看 Celery 日志）')
  }

  async function deleteDocument(kbId: number, docId: number) {
    await kbApi.deleteDocument(kbId, docId)
    documents.value = documents.value.filter((d) => d.id !== docId)
  }

  return {
    knowledgeBases,
    documents,
    loading,
    fetchKnowledgeBases,
    createKnowledgeBase,
    updateKnowledgeBase,
    deleteKnowledgeBase,
    fetchDocuments,
    uploadDocument,
    deleteDocument,
  }
})
