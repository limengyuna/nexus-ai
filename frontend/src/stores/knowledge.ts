/**
 * 知识库 + 文档状态管理
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

import * as kbApi from '@/api/knowledge'
import type { DocumentItem, KnowledgeBase, KnowledgeBaseCreate, KnowledgeBaseUpdate, TaskRecord } from '@/api/knowledge'

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
  ) {
    const { task } = await kbApi.uploadDocument(kbId, file)
    // 轮询任务进度
    return pollTask(task.id, onProgress)
  }

  async function pollTask(
    taskId: number,
    onProgress?: (task: TaskRecord) => void,
  ): Promise<TaskRecord> {
    for (let i = 0; i < 120; i++) {
      const t = await kbApi.getTask(taskId)
      onProgress?.(t)
      if (t.status === 'success' || t.status === 'failed' || t.status === 'cancelled') {
        return t
      }
      await new Promise((r) => setTimeout(r, 1000))
    }
    throw new Error('任务超时')
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
