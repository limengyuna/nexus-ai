/**
 * 记忆管理状态 (Pinia Store)
 *
 * 维护：当前用户的 L2 语义事实记忆列表、加载状态、过滤条件
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { MemoryFact } from '@/api/memory'
import * as memoryApi from '@/api/memory'

export const useMemoryStore = defineStore('memory', () => {
  // ---------- 状态 ----------
  const facts = ref<MemoryFact[]>([])
  const loading = ref(false)
  const filterType = ref<string | null>(null)

  // ---------- 计算属性 ----------
  /** 按当前筛选条件过滤后的记忆列表 */
  const filteredFacts = computed(() => {
    if (!filterType.value) return facts.value
    return facts.value.filter((f) => f.fact_type === filterType.value)
  })

  /** 各类型记忆计数统计 */
  const typeStats = computed(() => {
    const stats: Record<string, number> = {}
    for (const f of facts.value) {
      stats[f.fact_type] = (stats[f.fact_type] || 0) + 1
    }
    return stats
  })

  // ---------- Actions ----------
  async function fetchFacts(params?: { kbId?: number; scope?: 'global' | 'kb' }) {
    loading.value = true
    try {
      facts.value = await memoryApi.listFacts(params)
    } finally {
      loading.value = false
    }
  }

  async function removeFact(factId: number) {
    await memoryApi.deleteFact(factId)
    facts.value = facts.value.filter((f) => f.id !== factId)
  }

  function setFilter(type: string | null) {
    filterType.value = type
  }

  return {
    facts,
    loading,
    filterType,
    filteredFacts,
    typeStats,
    fetchFacts,
    removeFact,
    setFilter,
  }
})
