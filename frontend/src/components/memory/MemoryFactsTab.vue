<script setup lang="ts">
import { ref, computed } from 'vue'
import { Brain, Trash2, AlertTriangle, Settings, Heart, BookOpen, RefreshCw, Globe, Database } from 'lucide-vue-next'
import { useMemoryStore } from '@/stores/memory'

const memory = useMemoryStore()

const scopeFilter = ref<'all' | 'global' | 'kb'>('all')
const deletingId = ref<number | null>(null)
const confirmingDeleteId = ref<number | null>(null)

const typeConfig: Record<string, { label: string; color: string; bgColor: string; icon: any }> = {
  error_lesson: {
    label: '错误教训',
    color: 'text-zinc-700 dark:text-zinc-300',
    bgColor: 'bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700',
    icon: AlertTriangle,
  },
  env_constraint: {
    label: '环境约束',
    color: 'text-zinc-700 dark:text-zinc-300',
    bgColor: 'bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700',
    icon: Settings,
  },
  preference: {
    label: '用户偏好',
    color: 'text-zinc-700 dark:text-zinc-300',
    bgColor: 'bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700',
    icon: Heart,
  },
  knowledge: {
    label: '知识记录',
    color: 'text-zinc-700 dark:text-zinc-300',
    bgColor: 'bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700',
    icon: BookOpen,
  },
}

function getTypeConfig(type: string) {
  return typeConfig[type] || { label: type, color: 'text-zinc-600', bgColor: 'bg-zinc-100', icon: Brain }
}

const allTypes = computed(() => Object.keys(typeConfig))

function switchScope(scope: 'all' | 'global' | 'kb') {
  scopeFilter.value = scope
  if (scopeFilter.value === 'all') {
    memory.fetchFacts()
  } else {
    memory.fetchFacts({ scope: scopeFilter.value })
  }
}

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '未知'
  const d = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) {
    return `今天 ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
  } else if (diffDays === 1) {
    return `昨天 ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
  } else if (diffDays < 7) {
    return `${diffDays} 天前`
  } else {
    return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
  }
}

function startDelete(factId: number) {
  confirmingDeleteId.value = factId
}
function cancelDelete() {
  confirmingDeleteId.value = null
}
async function confirmDelete(factId: number) {
  deletingId.value = factId
  try {
    await memory.removeFact(factId)
  } finally {
    deletingId.value = null
    confirmingDeleteId.value = null
  }
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- 范围筛选与类型过滤 -->
    <div class="flex flex-wrap items-center gap-2 mb-6">
      <div class="flex flex-wrap items-center gap-1 mr-2 pr-3 border-r border-zinc-200 dark:border-zinc-700">
        <button
          @click="switchScope('all')"
          class="px-2.5 py-1 rounded text-xs font-medium transition-all duration-200"
          :class="scopeFilter === 'all'
            ? 'bg-zinc-900 dark:bg-zinc-200 text-white dark:text-zinc-900'
            : 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'"
        >
          全部范围
        </button>
        <button
          @click="switchScope('global')"
          class="px-2.5 py-1 rounded text-xs font-medium transition-all duration-200 flex items-center gap-1"
          :class="scopeFilter === 'global'
            ? 'bg-zinc-900 dark:bg-zinc-200 text-white dark:text-zinc-900'
            : 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'"
        >
          <Globe :size="11" />
          全局
        </button>
        <button
          @click="switchScope('kb')"
          class="px-2.5 py-1 rounded text-xs font-medium transition-all duration-200 flex items-center gap-1"
          :class="scopeFilter === 'kb'
            ? 'bg-zinc-900 dark:bg-zinc-200 text-white dark:text-zinc-900'
            : 'text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800'"
        >
          <Database :size="11" />
          知识库专属
        </button>
      </div>
      <button
        @click="memory.setFilter(null)"
        class="px-3 py-1.5 rounded-full text-xs font-medium transition-colors"
        :class="memory.filterType === null
          ? 'bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900'
          : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'"
      >
        全部 ({{ memory.facts.length }})
      </button>
      <button
        v-for="t in allTypes"
        :key="t"
        @click="memory.setFilter(memory.filterType === t ? null : t)"
        class="px-3 py-1.5 rounded-full text-xs font-medium transition-colors flex items-center gap-1.5"
        :class="memory.filterType === t
          ? `${getTypeConfig(t).bgColor} ${getTypeConfig(t).color} ring-1 ring-zinc-400`
          : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 hover:bg-zinc-200 dark:hover:bg-zinc-700'"
      >
        <component :is="getTypeConfig(t).icon" :size="12" :stroke-width="2" />
        {{ getTypeConfig(t).label }}
        <span v-if="memory.typeStats[t]" class="opacity-70">({{ memory.typeStats[t] }})</span>
      </button>
    </div>

    <!-- 事实记忆列表 -->
    <div v-if="memory.loading && memory.facts.length === 0" class="flex items-center justify-center h-48">
      <div class="flex items-center gap-3 text-zinc-400">
        <RefreshCw :size="18" class="animate-spin" />
        <span class="text-sm">加载记忆数据中...</span>
      </div>
    </div>
    <div v-else-if="memory.filteredFacts.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
      <Brain :size="40" :stroke-width="1.5" class="text-zinc-300 dark:text-zinc-600 mb-3" />
      <p class="text-sm text-zinc-500 dark:text-zinc-400">
        {{ memory.filterType ? '该类型下暂无事实' : '暂无长期记忆' }}
      </p>
      <p class="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
        继续与 Agent 对话，系统会自动学习并存储语义事实记忆。
      </p>
    </div>
    <div v-else class="grid gap-4 max-w-4xl">
      <div
        v-for="fact in memory.filteredFacts"
        :key="fact.id"
        class="group bg-white dark:bg-zinc-900/40 rounded-xl p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 ring-1 ring-black/[0.03] dark:ring-white/[0.05] transition-all duration-300"
      >
        <!-- 事实项卡片头部 -->
        <div class="flex items-center justify-between mb-2">
          <div class="flex items-center gap-2">
            <span
              class="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium"
              :class="`${getTypeConfig(fact.fact_type).bgColor} ${getTypeConfig(fact.fact_type).color}`"
            >
              <component :is="getTypeConfig(fact.fact_type).icon" :size="11" />
              {{ getTypeConfig(fact.fact_type).label }}
            </span>
            <span class="text-[10px] text-zinc-400 dark:text-zinc-500 flex items-center gap-1">
              重要性:
              <span class="inline-block w-16 h-1 bg-zinc-200 dark:bg-zinc-800 rounded-full overflow-hidden">
                <span
                  class="block h-full bg-zinc-800 dark:bg-zinc-200 transition-all"
                  :style="{ width: `${fact.importance * 100}%` }"
                />
              </span>
              {{ (fact.importance * 100).toFixed(0) }}%
            </span>
          </div>
          
          <!-- 快捷删除 -->
          <div class="flex items-center gap-2">
            <template v-if="confirmingDeleteId === fact.id">
              <span class="text-xs text-rose-500 font-medium">确认丢弃此记忆？</span>
              <button
                @click="confirmDelete(fact.id)"
                class="px-2 py-0.5 text-xs bg-rose-600 text-white dark:text-zinc-950 rounded hover:bg-rose-700"
                :disabled="deletingId === fact.id"
              >
                确认
              </button>
              <button @click="cancelDelete" class="px-2 py-0.5 text-xs bg-zinc-100 dark:bg-zinc-800 rounded hover:bg-zinc-200">
                取消
              </button>
            </template>
            <button
              v-else
              @click="startDelete(fact.id)"
              class="p-1 rounded text-zinc-400 hover:text-rose-600 dark:hover:text-rose-400 opacity-0 group-hover:opacity-100 hover:bg-rose-50 dark:hover:bg-rose-950/20 transition-all duration-200"
            >
              <Trash2 :size="13" />
            </button>
          </div>
        </div>
        
        <p class="text-sm text-zinc-800 dark:text-zinc-200 leading-relaxed whitespace-pre-wrap">{{ fact.content }}</p>
        
        <!-- 元数据区 -->
        <div class="flex items-center justify-between mt-3 pt-2.5 border-t border-zinc-100 dark:border-zinc-800/60">
          <div class="flex items-center gap-3 text-[10px] text-zinc-400 dark:text-zinc-500">
            <span v-if="fact.kb_id" class="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 border border-zinc-200 dark:border-zinc-700">
              <Database :size="9" class="inline mr-0.5" />
              KB#{{ fact.kb_id }}
            </span>
            <span v-else class="px-1.5 py-0.5 rounded bg-zinc-50 dark:bg-zinc-800/40 text-zinc-500">
              <Globe :size="9" class="inline mr-0.5" />
              全局记忆
            </span>
            <span>创建于 {{ formatDate(fact.created_at) }}</span>
            <span v-if="fact.access_count > 0">被调用 {{ fact.access_count }} 次</span>
          </div>
          <span class="text-[10px] text-zinc-300 dark:text-zinc-600 font-mono">#{{ fact.id }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
