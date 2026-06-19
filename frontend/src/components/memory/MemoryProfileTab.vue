<script setup lang="ts">
import { ref, computed } from 'vue'
import { RefreshCw, User, Sliders, BookOpen, Layers, Globe, Shield, X, Check, Plus, Edit2 } from 'lucide-vue-next'
import { useMemoryStore } from '@/stores/memory'

const memory = useMemoryStore()

import { defaultSlots } from '@/constants/memory'

// 槽位分类配置
const slotCategories: Record<string, { label: string; color: string; icon: any }> = {
  profile: { label: '画像基础 (Persona)', color: 'text-zinc-600 dark:text-zinc-400', icon: User },
  agent: { label: '交互习惯 (Agent Behavior)', color: 'text-blue-600 dark:text-blue-400', icon: Sliders },
  knowledge: { label: '知识检索 (RAG Settings)', color: 'text-emerald-600 dark:text-emerald-400', icon: BookOpen },
  output: { label: '格式偏好 (Output Layout)', color: 'text-amber-600 dark:text-amber-400', icon: Layers },
  domain: { label: '专注领域 (Business Domain)', color: 'text-indigo-600 dark:text-indigo-400', icon: Globe },
  constraint: { label: '安全约束 (Hard Constraints)', color: 'text-rose-600 dark:text-rose-400', icon: Shield }
}

const editingSlotKey = ref<string | null>(null)
const editingSlotValue = ref<any>(null)

// 格式化辅助函数
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

// 将白名单定义与已保存值合并
const allSlotsWithValues = computed(() => {
  return defaultSlots.map((dSlot) => {
    const matched = memory.profileValues.find((p) => p.slot_key === dSlot.key)
    return {
      ...dSlot,
      hasValue: !!matched,
      slot_value: matched ? matched.slot_value : null,
      confidence: matched ? matched.confidence : 0,
      source: matched ? matched.source : 'unset',
      updated_at: matched ? matched.updated_at : null
    }
  })
})

// 分组聚合槽位
const groupedSlots = computed(() => {
  const groups: Record<string, typeof allSlotsWithValues.value> = {}
  Object.keys(slotCategories).forEach((cat) => {
    groups[cat] = allSlotsWithValues.value.filter((s) => s.type === cat)
  })
  return groups
})

function startEditSlot(slot: any) {
  editingSlotKey.value = slot.key
  editingSlotValue.value = slot.hasValue ? slot.slot_value : (slot.valType === 'boolean' ? false : '')
}

function cancelEditSlot() {
  editingSlotKey.value = null
  editingSlotValue.value = null
}

async function saveSlotValue(slotKey: string, slotType: string) {
  let val = editingSlotValue.value
  // 如果是布尔值，需要强制类型转换
  if (allSlotsWithValues.value.find((s) => s.key === slotKey)?.valType === 'boolean') {
    val = val === true || val === 'true'
  }
  
  try {
    await memory.updateProfile(slotKey, val, 'manual')
    cancelEditSlot()
  } catch (err) {
    console.error('保存槽位失败:', err)
  }
}

async function clearSlotValue(slotKey: string) {
  if (confirm(`确认要清空该偏好配置（${slotKey}）吗？`)) {
    try {
      await memory.deleteProfile(slotKey)
    } catch (err) {
      console.error('清空槽位失败:', err)
    }
  }
}
</script>

<template>
  <div class="h-full flex flex-col max-w-6xl">
    <div v-if="memory.profileLoading" class="flex items-center justify-center h-48">
      <div class="flex items-center gap-3 text-zinc-400">
        <RefreshCw :size="18" class="animate-spin" />
        <span class="text-sm">同步结构化档案数据中...</span>
      </div>
    </div>

    <div v-else class="space-y-8">
      <!-- 槽位按分类循环展示 -->
      <div v-for="(catKey, catVal) in slotCategories" :key="catVal" class="space-y-4">
        <!-- 大分类标题：去除下划线，依靠负空间呼吸感分隔 -->
        <div class="flex items-center gap-2.5 pb-1 pt-4">
          <div class="w-6 h-6 rounded bg-zinc-100 dark:bg-zinc-800 flex items-center justify-center shadow-xs">
            <component :is="catKey.icon" :size="13" class="text-zinc-700 dark:text-zinc-300" />
          </div>
          <h2 class="text-base font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">{{ catKey.label }}</h2>
        </div>

        <!-- 分组卡片列表 -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          <div 
            v-for="slot in groupedSlots[catVal]" 
            :key="slot.key"
            class="bg-white dark:bg-zinc-900/40 rounded-xl p-5 flex flex-col justify-between shadow-sm hover:shadow-md hover:-translate-y-0.5 ring-1 ring-black/[0.03] dark:ring-white/[0.05] transition-all duration-300"
          >
            <!-- 卡片头部 -->
            <div>
              <div class="flex items-start justify-between">
                <div>
                  <div class="flex items-center gap-2 flex-wrap mb-1.5">
                    <h3 class="text-sm font-bold text-zinc-900 dark:text-zinc-100 flex items-center gap-1.5">
                      {{ slot.name }}
                      <!-- 活跃状态气泡 -->
                      <span 
                        class="inline-block w-1.5 h-1.5 rounded-full" 
                        :class="slot.hasValue ? 'bg-emerald-500 shadow-sm shadow-emerald-500/50' : 'bg-zinc-300 dark:bg-zinc-700'"
                      />
                    </h3>
                    <span class="px-1.5 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 text-[9px] font-mono font-medium text-zinc-500 tracking-wider">
                      {{ slot.key }}
                    </span>
                  </div>
                </div>

                <!-- 移除值操作 -->
                <button 
                  v-if="slot.hasValue"
                  @click="clearSlotValue(slot.key)"
                  class="text-zinc-400 hover:text-rose-500 p-1.5 hover:bg-rose-50 dark:hover:bg-rose-950/30 rounded-md transition-all duration-200 opacity-0 group-hover:opacity-100 flex-shrink-0"
                  title="重置此偏好"
                >
                  <X :size="14" />
                </button>
              </div>

              <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-1 leading-relaxed">{{ slot.desc }}</p>
            </div>

            <!-- 当前设定值与就地编辑逻辑 -->
            <div class="mt-5 pt-3 border-t border-zinc-100 dark:border-zinc-800/40">
              <div v-if="editingSlotKey === slot.key" class="flex items-center gap-2">
                <!-- 根据槽位值类型展示不同的编辑组件 -->
                <select 
                  v-if="slot.valType === 'enum'" 
                  v-model="editingSlotValue"
                  class="flex-1 bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/50 text-xs rounded-md px-2.5 py-1.5 text-zinc-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                >
                  <option v-for="opt in slot.options" :key="opt" :value="opt">{{ opt }}</option>
                </select>
                <select 
                  v-else-if="slot.valType === 'boolean'" 
                  v-model="editingSlotValue"
                  class="flex-1 bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/50 text-xs rounded-md px-2.5 py-1.5 text-zinc-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                >
                  <option :value="true">是 (True)</option>
                  <option :value="false">否 (False)</option>
                </select>
                <input 
                  v-else 
                  type="text" 
                  v-model="editingSlotValue"
                  class="flex-1 bg-zinc-50 dark:bg-zinc-800/50 border border-zinc-200 dark:border-zinc-700/50 text-xs rounded-md px-2.5 py-1.5 text-zinc-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-400"
                  placeholder="输入配置值..."
                />

                <!-- 确认与取消 -->
                <button 
                  @click="saveSlotValue(slot.key, slot.type)"
                  class="p-1.5 bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded-md hover:opacity-90 transition-opacity shadow-sm"
                >
                  <Check :size="13" />
                </button>
                <button 
                  @click="cancelEditSlot"
                  class="p-1.5 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-md hover:bg-zinc-50 dark:hover:bg-zinc-700 shadow-sm"
                >
                  <X :size="13" />
                </button>
              </div>

              <div v-else class="flex items-center justify-between">
                <!-- 显示已设定的内容 -->
                <div v-if="slot.hasValue">
                  <div class="text-xs font-semibold text-zinc-800 dark:text-zinc-100 flex items-center gap-1.5">
                    <span class="font-mono px-1">
                      {{ slot.slot_value }}
                    </span>
                    <!-- 来源渠道标识 -->
                    <span 
                      class="px-1.5 py-0.5 text-[8px] rounded-full uppercase tracking-wider font-bold"
                      :class="slot.source === 'manual' 
                        ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400' 
                        : 'bg-emerald-50 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'"
                    >
                      {{ slot.source === 'manual' ? '手工' : '大模型' }}
                    </span>
                  </div>
                  <p class="text-[9px] text-zinc-400 dark:text-zinc-500 mt-1 pl-1">
                    置信度: {{ (slot.confidence * 100).toFixed(0) }}% | 更新于 {{ formatDate(slot.updated_at) }}
                  </p>
                </div>
                <div v-else class="text-xs text-zinc-400 italic pl-1">
                  未设定偏好
                </div>

                <!-- 开始编辑按钮 -->
                <button 
                  @click="startEditSlot(slot)"
                  class="text-xs flex items-center gap-1 px-2.5 py-1.5 rounded-md text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 dark:hover:text-zinc-100 dark:hover:bg-zinc-800 transition-colors"
                >
                  <Plus v-if="!slot.hasValue" :size="12" />
                  <Edit2 v-else :size="12" />
                  <span class="font-medium">{{ slot.hasValue ? '修改' : '设定' }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
