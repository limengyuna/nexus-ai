/**
 * 记忆管理状态 (Pinia Store)
 *
 * 维护：当前用户的 L2 语义事实记忆列表、加载状态、过滤条件
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import type { MemoryFact, ProfileSlotItem, MemoryCandidateItem } from '@/api/memory'
import * as memoryApi from '@/api/memory'

export const useMemoryStore = defineStore('memory', () => {
  // ---------- 状态 ----------
  const facts = ref<MemoryFact[]>([])
  const loading = ref(false)
  const filterType = ref<string | null>(null)

  const profileValues = ref<ProfileSlotItem[]>([])
  const candidates = ref<MemoryCandidateItem[]>([])
  const profileLoading = ref(false)
  const candidatesLoading = ref(false)

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

  async function fetchProfile(params?: { slotType?: string }) {
    profileLoading.value = true
    try {
      profileValues.value = await memoryApi.listProfileValues(params)
    } finally {
      profileLoading.value = false
    }
  }

  async function updateProfile(slotKey: string, slotValue: any, source = 'manual') {
    const updated = await memoryApi.updateProfileValue(slotKey, slotValue, source)
    const idx = profileValues.value.findIndex((p) => p.slot_key === slotKey)
    if (idx >= 0) {
      profileValues.value[idx] = updated
    } else {
      profileValues.value.push(updated)
    }
  }

  async function deleteProfile(slotKey: string) {
    await memoryApi.deleteProfileValue(slotKey)
    profileValues.value = profileValues.value.filter((p) => p.slot_key !== slotKey)
  }

  async function fetchCandidates() {
    candidatesLoading.value = true
    try {
      candidates.value = await memoryApi.listCandidates()
    } finally {
      candidatesLoading.value = false
    }
  }

  async function confirmCandidate(candidateId: number, accept: boolean, slotValue?: any) {
    if (accept) {
      const activeSlot = await memoryApi.acceptCandidate(candidateId, slotValue)
      const idx = profileValues.value.findIndex((p) => p.slot_key === activeSlot.slot_key)
      if (idx >= 0) {
        profileValues.value[idx] = activeSlot
      } else {
        profileValues.value.push(activeSlot)
      }
    } else {
      await memoryApi.rejectCandidate(candidateId)
    }
    candidates.value = candidates.value.filter((c) => c.id !== candidateId)
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
    profileValues,
    candidates,
    profileLoading,
    candidatesLoading,
    fetchProfile,
    updateProfile,
    deleteProfile,
    fetchCandidates,
    confirmCandidate,
  }
})

