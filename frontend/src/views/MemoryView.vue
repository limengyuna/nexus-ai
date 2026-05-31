<script setup lang="ts">
/**
 * L2 记忆管理页面
 *
 * 展示当前用户的所有长期语义事实记忆，支持按类型筛选、查看详情和删除。
 */
import { onMounted, ref, computed } from 'vue'
import { Brain, Trash2, AlertTriangle, Settings, Heart, BookOpen, RefreshCw, Globe, Database } from 'lucide-vue-next'
import { useMemoryStore } from '@/stores/memory'

const memory = useMemoryStore()

// 删除确认相关
const deletingId = ref<number | null>(null)
const confirmingDeleteId = ref<number | null>(null)

// 范围筛选：全部 / 全局记忆 / 知识库专属
const scopeFilter = ref<'all' | 'global' | 'kb'>('all')

onMounted(() => {
  memory.fetchFacts()
})

function switchScope(scope: 'all' | 'global' | 'kb') {
  scopeFilter.value = scope
  if (scope === 'all') memory.fetchFacts()
  else memory.fetchFacts({ scope })
}

// 类型显示配置
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
  return typeConfig[type] || { label: type, color: 'text-gray-700', bgColor: 'bg-gray-100', icon: Brain }
}

// 所有类型的列表（用于过滤器按钮）
const allTypes = computed(() => {
  return Object.keys(typeConfig)
})

function formatDate(dateStr: string): string {
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

function formatImportance(importance: number): string {
  return (importance * 100).toFixed(0) + '%'
}

// 删除操作：先确认再删
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
  <div class="h-full flex flex-col bg-gray-50 dark:bg-gray-950">
    <!-- 顶部标题栏 -->
    <header class="flex-shrink-0 border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 px-8 py-5">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-md bg-zinc-900 dark:bg-zinc-100 text-zinc-100 dark:text-zinc-900 text-white dark:text-zinc-900 flex items-center justify-center shadow-sm">
            <Brain :size="20" :stroke-width="2" />
          </div>
          <div>
            <h1 class="text-lg font-semibold text-gray-900 dark:text-gray-100">长期记忆</h1>
            <p class="text-xs text-gray-500 dark:text-gray-400">
              Agent 从历史交互中学到的 {{ memory.facts.length }} 条语义事实
            </p>
          </div>
        </div>
        <button
          @click="memory.fetchFacts()"
          class="flex items-center gap-2 px-3 py-2 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-sm transition-colors"
          :class="{ 'animate-spin': memory.loading }"
        >
          <RefreshCw :size="16" :stroke-width="2" :class="{ 'animate-spin': memory.loading }" />
          <span v-if="!memory.loading">刷新</span>
        </button>
      </div>

      <!-- 范围筛选：全部 / 全局 / 知识库专属 -->
      <div class="flex items-center gap-2 mt-4">
        <div class="flex items-center gap-1 mr-2 pr-3 border-r border-gray-200 dark:border-gray-700">
          <button
            @click="switchScope('all')"
            class="px-2.5 py-1 rounded-md text-xs font-medium transition-colors"
            :class="scopeFilter === 'all'
              ? 'bg-gray-800 dark:bg-gray-200 text-white dark:text-zinc-900 dark:text-gray-900'
              : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'"
          >
            全部
          </button>
          <button
            @click="switchScope('global')"
            class="px-2.5 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1"
            :class="scopeFilter === 'global'
              ? 'bg-gray-800 dark:bg-gray-200 text-white dark:text-zinc-900 dark:text-gray-900'
              : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'"
          >
            <Globe :size="11" />
            全局
          </button>
          <button
            @click="switchScope('kb')"
            class="px-2.5 py-1 rounded-md text-xs font-medium transition-colors flex items-center gap-1"
            :class="scopeFilter === 'kb'
              ? 'bg-gray-800 dark:bg-gray-200 text-white dark:text-zinc-900 dark:text-gray-900'
              : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800'"
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
            : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'"
        >
          全部 ({{ memory.facts.length }})
        </button>
        <button
          v-for="t in allTypes"
          :key="t"
          @click="memory.setFilter(memory.filterType === t ? null : t)"
          class="px-3 py-1.5 rounded-full text-xs font-medium transition-colors flex items-center gap-1.5"
          :class="memory.filterType === t
            ? `${getTypeConfig(t).bgColor} ${getTypeConfig(t).color} ring-1 ring-current`
            : 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700'"
        >
          <component :is="getTypeConfig(t).icon" :size="12" :stroke-width="2" />
          {{ getTypeConfig(t).label }}
          <span v-if="memory.typeStats[t]" class="opacity-70">({{ memory.typeStats[t] }})</span>
        </button>
      </div>
    </header>

    <!-- 内容区 -->
    <div class="flex-1 overflow-y-auto px-8 py-6">
      <!-- 加载态 -->
      <div v-if="memory.loading && memory.facts.length === 0" class="flex items-center justify-center h-48">
        <div class="flex items-center gap-3 text-gray-400 dark:text-gray-500">
          <RefreshCw :size="20" class="animate-spin" />
          <span class="text-sm">加载记忆中...</span>
        </div>
      </div>

      <!-- 空态 -->
      <div v-else-if="memory.filteredFacts.length === 0" class="flex flex-col items-center justify-center h-48 text-center">
        <Brain :size="40" :stroke-width="1.5" class="text-gray-300 dark:text-gray-600 mb-3" />
        <p class="text-sm text-gray-500 dark:text-gray-400">
          {{ memory.filterType ? '该类型下暂无记忆' : '暂无长期记忆' }}
        </p>
        <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">
          继续与 Agent 对话，系统会自动从交互中提取有价值的事实
        </p>
      </div>

      <!-- 记忆卡片列表 -->
      <div v-else class="grid gap-4 max-w-4xl">
        <div
          v-for="fact in memory.filteredFacts"
          :key="fact.id"
          class="group bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-md p-4 hover:border-zinc-400 hover:border-gray-300 dark:hover:border-gray-700 transition-all duration-200"
        >
          <!-- 卡片头部：类型标签 + 重要性 + 操作 -->
          <div class="flex items-center justify-between mb-2.5">
            <div class="flex items-center gap-2">
              <span
                class="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium"
                :class="`${getTypeConfig(fact.fact_type).bgColor} ${getTypeConfig(fact.fact_type).color}`"
              >
                <component :is="getTypeConfig(fact.fact_type).icon" :size="11" :stroke-width="2" />
                {{ getTypeConfig(fact.fact_type).label }}
              </span>
              <!-- 重要性指示 -->
              <span class="text-[10px] text-gray-400 dark:text-gray-500 flex items-center gap-1">
                重要性
                <span class="inline-block w-16 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                  <span
                    class="block h-full rounded-full transition-all"
                    :class="{
                      'bg-zinc-900 dark:bg-zinc-100': fact.importance >= 0.8,
                      'bg-zinc-500 dark:bg-zinc-400': fact.importance >= 0.5 && fact.importance < 0.8,
                      'bg-gray-400': fact.importance < 0.5,
                    }"
                    :style="{ width: `${fact.importance * 100}%` }"
                  />
                </span>
                {{ formatImportance(fact.importance) }}
              </span>
            </div>

            <!-- 删除按钮 -->
            <div class="flex items-center gap-2">
              <template v-if="confirmingDeleteId === fact.id">
                <span class="text-xs text-red-600 dark:text-red-400">确认删除？</span>
                <button
                  @click="confirmDelete(fact.id)"
                  class="px-2 py-1 text-xs bg-red-600 text-white dark:text-zinc-900 rounded hover:bg-red-700 transition-colors"
                  :disabled="deletingId === fact.id"
                >
                  {{ deletingId === fact.id ? '删除中...' : '确认' }}
                </button>
                <button
                  @click="cancelDelete()"
                  class="px-2 py-1 text-xs bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                >
                  取消
                </button>
              </template>
              <button
                v-else
                @click="startDelete(fact.id)"
                class="p-1.5 rounded-sm text-gray-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 opacity-0 group-hover:opacity-100 transition-all"
                title="删除此记忆"
              >
                <Trash2 :size="14" :stroke-width="2" />
              </button>
            </div>
          </div>

          <!-- 事实内容 -->
          <p class="text-sm text-gray-800 dark:text-gray-200 leading-relaxed whitespace-pre-wrap">{{ fact.content }}</p>

          <!-- 卡片底部元数据 -->
          <div class="flex items-center justify-between mt-3 pt-2.5 border-t border-gray-100 dark:border-gray-800">
            <div class="flex items-center gap-3 text-[10px] text-gray-400 dark:text-gray-500">
              <span
                v-if="fact.kb_id"
                class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-700"
              >
                <Database :size="9" />
                KB#{{ fact.kb_id }}
              </span>
              <span
                v-else
                class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-gray-50 dark:bg-gray-800 text-gray-500 dark:text-gray-400"
              >
                <Globe :size="9" />
                全局
              </span>
              <span>创建于 {{ formatDate(fact.created_at) }}</span>
              <span v-if="fact.access_count > 0">
                被引用 {{ fact.access_count }} 次
              </span>
              <span v-if="fact.last_accessed_at">
                最近引用 {{ formatDate(fact.last_accessed_at) }}
              </span>
            </div>
            <span class="text-[10px] text-gray-300 dark:text-gray-600 font-mono">#{{ fact.id }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
