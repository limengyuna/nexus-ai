<script setup lang="ts">
/**
 * 记忆管理页面 (MemoryView.vue)
 *
 * 全面重构为三 Tab 联动记忆管理面板：
 * 1. 长期记忆事实 (L2 Facts) - 保留原有模糊记忆功能，支持类型筛选
 * 2. 结构化用户档案 (Profile Slots) - 可视化用户画像卡片配置板，支持分组管理、就地编辑与快捷重置
 * 3. 候选偏好确认 (Candidates) - LLM 自动提取的偏好预备区，支持就地采纳（可编辑修改）与拒绝，高颜值微交互
 */
import { onMounted, ref, computed } from 'vue'
import {
  Brain,
  Trash2,
  AlertTriangle,
  Settings,
  Heart,
  BookOpen,
  RefreshCw,
  Globe,
  Database,
  User,
  Sliders,
  Check,
  X,
  Edit2,
  Sparkles,
  Plus,
  Shield,
  Layers,
  HelpCircle
} from 'lucide-vue-next'
import { useMemoryStore } from '@/stores/memory'
import type { ProfileSlotItem, MemoryCandidateItem } from '@/api/memory'

const memory = useMemoryStore()

// 当前激活的面板：facts (长期记忆事实) / profile (结构化画像) / candidates (偏好候选审核)
const activeTab = ref<'facts' | 'profile' | 'candidates'>('facts')

// --- 长期记忆 (L2 Facts) 相关状态 ---
const deletingId = ref<number | null>(null)
const confirmingDeleteId = ref<number | null>(null)
const scopeFilter = ref<'all' | 'global' | 'kb'>('all')

// --- 结构化档案 (Profile Slots) 相关状态 ---
// 预置的系统白名单槽位定义，用于将未设定的槽位和已设定的槽位合并展示，形成完整的“控制中心”
const defaultSlots = [
  { key: 'profile.role', name: '用户角色', type: 'profile', desc: '用户在组织或工作中的角色定位', valType: 'string' },
  { key: 'profile.primary_language', name: '偏好交流语言', type: 'profile', desc: '用户与 AI 沟通时偏好的主要语言', valType: 'string' },
  { key: 'agent.response_style', name: '回答风格偏好', type: 'agent', desc: '系统回答的文风与排版特点', valType: 'enum', options: ['concise', 'detailed', 'step_by_step', 'formal'] },
  { key: 'agent.detail_level', name: '回答详细程度', type: 'agent', desc: 'AI 生成内容的展开和详细程度', valType: 'enum', options: ['low', 'medium', 'high'] },
  { key: 'agent.autonomy_level', name: 'Agent 自主程度', type: 'agent', desc: '多步骤或敏感工具执行时的授权敏感度', valType: 'enum', options: ['conservative', 'ask_first', 'proactive'] },
  { key: 'agent.clarification_preference', name: '信息澄清偏好', type: 'agent', desc: '当用户意图含糊时，AI 偏向直接假设还是先提问', valType: 'enum', options: ['ask_first', 'assume_and_explain'] },
  { key: 'knowledge.preferred_citation_style', name: '引用呈现风格', type: 'knowledge', desc: '知识库 RAG 检索回答时的文献标注样式', valType: 'string' },
  { key: 'knowledge.answer_grounding_requirement', name: '无依据不回答', type: 'knowledge', desc: '严格限制 AI 只能回答有文档数据支撑的内容', valType: 'boolean' },
  { key: 'tool.approval_sensitivity', name: '工具审批敏感度', type: 'tool', desc: '定义哪些系统工具的调用必须弹出二次审批', valType: 'string' },
  { key: 'output.default_format', name: '默认输出格式', type: 'output', desc: 'AI 吐出回答的默认结构化格式', valType: 'enum', options: ['paragraph', 'list', 'table', 'markdown', 'json'] },
  { key: 'domain.business_domain', name: '聚焦业务领域', type: 'domain', desc: '用户长期关注或从事的特定垂直领域', valType: 'string' },
  { key: 'constraint.must_follow', name: '必须遵守的硬性规则', type: 'constraint', desc: '在任何会话中大模型均绝对不可违反的规则', valType: 'string' },
  { key: 'constraint.do_not_do', name: '严禁越界行为', type: 'constraint', desc: '用户明确禁止 AI 做出的行为、语气或操作', valType: 'string' },
  { key: 'constraint.data_sensitivity', name: '敏感数据处理偏好', type: 'constraint', desc: '对于敏感、保密或个人隐私信息的合规处理逻辑', valType: 'string' }
]

// 槽位分类配置
const slotCategories = {
  profile: { label: '画像基础 (Persona)', color: 'text-zinc-600 dark:text-zinc-400', icon: User },
  agent: { label: '交互习惯 (Agent Behavior)', color: 'text-blue-600 dark:text-blue-400', icon: Sliders },
  knowledge: { label: '知识检索 (RAG Settings)', color: 'text-emerald-600 dark:text-emerald-400', icon: BookOpen },
  tool: { label: '工具安全 (Tool Execution)', color: 'text-purple-600 dark:text-purple-400', icon: Settings },
  output: { label: '格式偏好 (Output Layout)', color: 'text-amber-600 dark:text-amber-400', icon: Layers },
  domain: { label: '专注领域 (Business Domain)', color: 'text-indigo-600 dark:text-indigo-400', icon: Globe },
  constraint: { label: '安全约束 (Hard Constraints)', color: 'text-rose-600 dark:text-rose-400', icon: Shield }
}

// 槽位编辑状态
const editingSlotKey = ref<string | null>(null)
const editingSlotValue = ref<any>(null)

// --- 候选偏好确认 (Candidates) 相关状态 ---
const processingCandidateId = ref<number | null>(null)
const reviewingCandidate = ref<MemoryCandidateItem | null>(null)
const candidateEditValue = ref<any>(null)

// --- 挂载与加载逻辑 ---
onMounted(() => {
  loadData()
})

function loadData() {
  if (activeTab.value === 'facts') {
    if (scopeFilter.value === 'all') memory.fetchFacts()
    else memory.fetchFacts({ scope: scopeFilter.value as 'global' | 'kb' })
  } else if (activeTab.value === 'profile') {
    memory.fetchProfile()
  } else if (activeTab.value === 'candidates') {
    memory.fetchCandidates()
  }
}

function switchTab(tab: 'facts' | 'profile' | 'candidates') {
  activeTab.value = tab
  loadData()
}

// --- 长期记忆 L2 Facts 配置项 ---
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
  loadData()
}

// --- 格式化辅助函数 ---
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

// --- 长期记忆删除 ---
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

// --- 结构化用户档案 Slot 管理 ---
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

// 开启编辑槽位
function startEditSlot(slot: any) {
  editingSlotKey.value = slot.key
  editingSlotValue.value = slot.hasValue ? slot.slot_value : (slot.valType === 'boolean' ? false : '')
}

// 取消编辑槽位
function cancelEditSlot() {
  editingSlotKey.value = null
  editingSlotValue.value = null
}

// 保存槽位值修改
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

// 重置/清除槽位值
async function clearSlotValue(slotKey: string) {
  if (confirm(`确认要清空该偏好配置（${slotKey}）吗？`)) {
    try {
      await memory.deleteProfile(slotKey)
    } catch (err) {
      console.error('清空槽位失败:', err)
    }
  }
}

// --- 候选偏好确认 (Candidates) 管理 ---
// 打开候选处理弹层/详情
function startReviewCandidate(candidate: MemoryCandidateItem) {
  reviewingCandidate.value = candidate
  candidateEditValue.value = candidate.suggested_value
}

function closeReviewCandidate() {
  reviewingCandidate.value = null
  candidateEditValue.value = null
}

// 执行采纳偏好候选
async function acceptPref(candidateId: number) {
  processingCandidateId.value = candidateId
  try {
    await memory.confirmCandidate(candidateId, true, candidateEditValue.value)
    closeReviewCandidate()
  } catch (err) {
    console.error('采纳偏好失败:', err)
  } finally {
    processingCandidateId.value = null
  }
}

// 执行拒绝偏好候选
async function rejectPref(candidateId: number) {
  if (confirm('确认拒绝该候选偏好提取？拒绝后本条建议将被丢弃。')) {
    processingCandidateId.value = candidateId
    try {
      await memory.confirmCandidate(candidateId, false)
      closeReviewCandidate()
    } catch (err) {
      console.error('拒绝偏好失败:', err)
    } finally {
      processingCandidateId.value = null
    }
  }
}
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50 dark:bg-zinc-950 font-sans">
    <!-- 顶部高端工业风标题栏 -->
    <header class="flex-shrink-0 border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-8 py-5">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded bg-zinc-900 dark:bg-zinc-100 text-zinc-100 dark:text-zinc-900 flex items-center justify-center shadow-sm">
            <Brain :size="20" :stroke-width="2" />
          </div>
          <div>
            <h1 class="text-lg font-semibold text-zinc-900 dark:text-zinc-100">层级记忆控制台</h1>
            <p class="text-xs text-zinc-500 dark:text-zinc-400">
              精确控制系统的全局偏好配置，并查看从自然会话中自动捕获的多维度用户画像
            </p>
          </div>
        </div>
        <button
          @click="loadData"
          class="flex items-center gap-2 px-3 py-2 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded transition-colors duration-200 border border-zinc-200 dark:border-zinc-800"
        >
          <RefreshCw :size="15" :stroke-width="2" />
          <span>刷新数据</span>
        </button>
      </div>

      <!-- 锌灰极简三 Tab 导航设计 -->
      <div class="flex items-center gap-1.5 mt-5 border-b border-zinc-100 dark:border-zinc-800/60 pb-1">
        <button
          @click="switchTab('facts')"
          class="relative px-4 py-2 text-sm font-medium transition-all duration-200"
          :class="activeTab === 'facts' 
            ? 'text-zinc-900 dark:text-zinc-100 border-b-2 border-zinc-900 dark:border-zinc-100 font-semibold' 
            : 'text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300'"
        >
          长期记忆事实 (L2 Facts)
        </button>
        <button
          @click="switchTab('profile')"
          class="relative px-4 py-2 text-sm font-medium transition-all duration-200 flex items-center gap-1.5"
          :class="activeTab === 'profile' 
            ? 'text-zinc-900 dark:text-zinc-100 border-b-2 border-zinc-900 dark:border-zinc-100 font-semibold' 
            : 'text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300'"
        >
          结构化用户档案 (Profile Slots)
          <span class="px-1.5 py-0.5 text-[10px] rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-500">
            {{ memory.profileValues.length }} / {{ defaultSlots.length }}
          </span>
        </button>
        <button
          @click="switchTab('candidates')"
          class="relative px-4 py-2 text-sm font-medium transition-all duration-200 flex items-center gap-1.5"
          :class="activeTab === 'candidates' 
            ? 'text-zinc-900 dark:text-zinc-100 border-b-2 border-zinc-900 dark:border-zinc-100 font-semibold' 
            : 'text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300'"
        >
          偏好审核候选区 (Candidates)
          <span 
            v-if="memory.candidates.length > 0" 
            class="px-1.5 py-0.5 text-[10px] rounded-full bg-rose-100 dark:bg-rose-950 text-rose-600 dark:text-rose-400 font-bold animate-pulse"
          >
            {{ memory.candidates.length }} 待审
          </span>
        </button>
      </div>
    </header>

    <!-- 主展示区 -->
    <div class="flex-1 overflow-y-auto px-8 py-6">
      
      <!-- ==================== TAB 1: 长期记忆事实 ==================== -->
      <div v-if="activeTab === 'facts'" class="h-full flex flex-col">
        <!-- 范围筛选与类型过滤 -->
        <div class="flex items-center gap-2 mb-6">
          <div class="flex items-center gap-1 mr-2 pr-3 border-r border-zinc-200 dark:border-zinc-700">
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
            class="group bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800/80 rounded p-4 hover:border-zinc-400 dark:hover:border-zinc-700 transition-all duration-200"
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

      <!-- ==================== TAB 2: 结构化画像档案 ==================== -->
      <div v-if="activeTab === 'profile'" class="h-full flex flex-col max-w-6xl">
        <div v-if="memory.profileLoading" class="flex items-center justify-center h-48">
          <div class="flex items-center gap-3 text-zinc-400">
            <RefreshCw :size="18" class="animate-spin" />
            <span class="text-sm">同步结构化档案数据中...</span>
          </div>
        </div>

        <div v-else class="space-y-8">
          <!-- 槽位按分类循环展示 -->
          <div v-for="(catKey, catVal) in slotCategories" :key="catVal" class="space-y-3">
            <div class="flex items-center gap-2 border-b border-zinc-200 dark:border-zinc-800 pb-2">
              <component :is="catKey.icon" :size="16" class="text-zinc-600 dark:text-zinc-400" />
              <h2 class="text-sm font-semibold text-zinc-800 dark:text-zinc-200">{{ catKey.label }}</h2>
            </div>

            <!-- 分组卡片列表 -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div 
                v-for="slot in groupedSlots[catVal]" 
                :key="slot.key"
                class="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded p-4 flex flex-col justify-between hover:border-zinc-300 dark:hover:border-zinc-700 transition-all duration-200"
              >
                <!-- 卡片头部：中文名 + Key -->
                <div>
                  <div class="flex items-start justify-between">
                    <div>
                      <h3 class="text-sm font-semibold text-zinc-800 dark:text-zinc-100 flex items-center gap-1.5">
                        {{ slot.name }}
                        <!-- 活跃状态气泡 -->
                        <span 
                          class="inline-block w-1.5 h-1.5 rounded-full" 
                          :class="slot.hasValue ? 'bg-emerald-500 shadow-sm shadow-emerald-500' : 'bg-zinc-300 dark:bg-zinc-700'"
                        />
                      </h3>
                      <p class="text-[10px] text-zinc-400 dark:text-zinc-500 font-mono mt-0.5">{{ slot.key }}</p>
                    </div>

                    <!-- 移除值操作 -->
                    <button 
                      v-if="slot.hasValue"
                      @click="clearSlotValue(slot.key)"
                      class="text-zinc-400 hover:text-rose-500 p-1 hover:bg-zinc-50 dark:hover:bg-zinc-800 rounded transition-all duration-150"
                      title="重置此偏好"
                    >
                      <X :size="14" />
                    </button>
                  </div>

                  <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-2 leading-relaxed">{{ slot.desc }}</p>
                </div>

                <!-- 当前设定值与就地编辑逻辑 -->
                <div class="mt-4 pt-3 border-t border-zinc-100 dark:border-zinc-800/80">
                  <div v-if="editingSlotKey === slot.key" class="flex items-center gap-2">
                    <!-- 根据槽位值类型展示不同的编辑组件 -->
                    <!-- 1. 枚举类型 -->
                    <select 
                      v-if="slot.valType === 'enum'" 
                      v-model="editingSlotValue"
                      class="flex-1 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-xs rounded px-2.5 py-1.5 text-zinc-800 dark:text-zinc-100 focus:outline-none"
                    >
                      <option v-for="opt in slot.options" :key="opt" :value="opt">{{ opt }}</option>
                    </select>
                    <!-- 2. 布尔类型 -->
                    <select 
                      v-else-if="slot.valType === 'boolean'" 
                      v-model="editingSlotValue"
                      class="flex-1 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-xs rounded px-2.5 py-1.5 text-zinc-800 dark:text-zinc-100 focus:outline-none"
                    >
                      <option :value="true">是 (True)</option>
                      <option :value="false">否 (False)</option>
                    </select>
                    <!-- 3. 普通文本类型 -->
                    <input 
                      v-else 
                      type="text" 
                      v-model="editingSlotValue"
                      class="flex-1 bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-xs rounded px-2.5 py-1.5 text-zinc-800 dark:text-zinc-100 focus:outline-none"
                      placeholder="输入配置值..."
                    />

                    <!-- 确认与取消 -->
                    <button 
                      @click="saveSlotValue(slot.key, slot.type)"
                      class="p-1.5 bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded hover:opacity-90 transition-opacity"
                    >
                      <Check :size="13" />
                    </button>
                    <button 
                      @click="cancelEditSlot"
                      class="p-1.5 bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded hover:bg-zinc-200 dark:hover:bg-zinc-700"
                    >
                      <X :size="13" />
                    </button>
                  </div>

                  <div v-else class="flex items-center justify-between">
                    <!-- 显示已设定的内容 -->
                    <div v-if="slot.hasValue">
                      <div class="text-xs font-semibold text-zinc-800 dark:text-zinc-100 flex items-center gap-1.5">
                        <span class="font-mono bg-zinc-100 dark:bg-zinc-800 px-2 py-1 rounded text-zinc-700 dark:text-zinc-300">
                          {{ slot.slot_value }}
                        </span>
                        <!-- 来源渠道标识 -->
                        <span 
                          class="px-1.5 py-0.5 text-[9px] rounded-full"
                          :class="slot.source === 'manual' 
                            ? 'bg-blue-50 dark:bg-blue-950 text-blue-500' 
                            : 'bg-zinc-100 dark:bg-zinc-800 text-zinc-500'"
                        >
                          {{ slot.source === 'manual' ? '用户手工' : '大模型提取' }}
                        </span>
                      </div>
                      <p class="text-[9px] text-zinc-400 dark:text-zinc-500 mt-1">
                        置信度: {{ (slot.confidence * 100).toFixed(0) }}% | 最后更新: {{ formatDate(slot.updated_at) }}
                      </p>
                    </div>
                    <div v-else class="text-xs text-zinc-400 italic">
                      未设定偏好
                    </div>

                    <!-- 开始编辑按钮 -->
                    <button 
                      @click="startEditSlot(slot)"
                      class="text-xs flex items-center gap-1 text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
                    >
                      <Plus v-if="!slot.hasValue" :size="12" />
                      <Edit2 v-else :size="12" />
                      <span>{{ slot.hasValue ? '修改' : '设定' }}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== TAB 3: 偏好候选确认区 ==================== -->
      <div v-if="activeTab === 'candidates'" class="h-full flex flex-col">
        <div v-if="memory.candidatesLoading" class="flex items-center justify-center h-48">
          <div class="flex items-center gap-3 text-zinc-400">
            <RefreshCw :size="18" class="animate-spin" />
            <span class="text-sm">检索候选偏好列表中...</span>
          </div>
        </div>

        <div v-else-if="memory.candidates.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
          <Sparkles :size="40" :stroke-width="1.5" class="text-zinc-300 dark:text-zinc-600 mb-3 animate-pulse" />
          <p class="text-sm text-zinc-500 dark:text-zinc-400">暂无待确认候选偏好</p>
          <p class="text-xs text-zinc-400 dark:text-zinc-500 mt-1 max-w-sm leading-relaxed">
            系统非常智能。当检测到用户的显式或隐式言语中流露出稳定的“习惯/约束/规则”（如希望输出格式、语调等）时，本区域会自动生成一条预备项，等待你的确认批准。
          </p>
        </div>

        <div v-else class="grid gap-6 max-w-4xl">
          <div 
            v-for="cand in memory.candidates" 
            :key="cand.id"
            class="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded p-5 flex flex-col justify-between hover:border-zinc-300 dark:hover:border-zinc-700 transition-all duration-200 relative overflow-hidden"
          >
            <!-- 气泡斜角背景：提取徽章 -->
            <div class="absolute top-0 right-0 bg-zinc-900 text-white dark:bg-zinc-200 dark:text-zinc-900 px-3 py-1 text-[9px] rounded-bl font-semibold uppercase tracking-wider flex items-center gap-1">
              <Sparkles :size="10" />
              <span>智能发现 (Suggested)</span>
            </div>

            <div>
              <!-- 槽位配置方向 -->
              <div class="flex items-center gap-2 mb-3">
                <span class="px-2 py-0.5 rounded bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-xs font-mono font-semibold text-zinc-700 dark:text-zinc-300">
                  {{ cand.suggested_slot_key }}
                </span>
                <span class="text-xs text-zinc-400">建议写入值:</span>
                <span class="text-xs font-mono font-bold bg-amber-50 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 px-2 py-0.5 rounded border border-amber-200/50 dark:border-amber-900/30">
                  {{ cand.suggested_value }}
                </span>
              </div>

              <!-- 理由描述 -->
              <p class="text-xs text-zinc-500 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-950/40 p-2.5 rounded leading-relaxed border border-zinc-100 dark:border-zinc-800/40 mb-4">
                <strong class="text-zinc-700 dark:text-zinc-300">提取理由：</strong>
                {{ cand.reason || '大模型在你的话语中发现并归纳了稳定的偏好设定。' }}
              </p>

              <!-- 依据上下文 -->
              <div class="mb-4">
                <h4 class="text-[11px] font-semibold text-zinc-400 dark:text-zinc-500 mb-1.5 uppercase">上下文会话依据 (Context)</h4>
                <blockquote class="text-xs text-zinc-600 dark:text-zinc-400 italic pl-3 border-l-2 border-zinc-300 dark:border-zinc-700 py-1.5 leading-relaxed bg-zinc-50/50 dark:bg-zinc-950/20 pr-3 rounded-r">
                  "{{ cand.candidate_text }}"
                </blockquote>
              </div>
            </div>

            <!-- 卡片底部信息 + 互动按钮 -->
            <div class="flex items-center justify-between pt-4 border-t border-zinc-100 dark:border-zinc-800/60">
              <div class="flex items-center gap-4 text-[10px] text-zinc-400 dark:text-zinc-500">
                <span>首次检测置信度: {{ (cand.confidence * 100).toFixed(0) }}%</span>
                <span>检测频次: 重复提及 {{ cand.seen_count }} 次</span>
                <span>发现时间: {{ formatDate(cand.created_at) }}</span>
              </div>

              <!-- 确认采纳或拒绝的微交互动作 -->
              <div class="flex items-center gap-2">
                <button
                  @click="rejectPref(cand.id)"
                  class="px-3 py-1.5 text-xs text-zinc-500 hover:text-rose-500 border border-zinc-200 dark:border-zinc-800 rounded hover:bg-rose-50 dark:hover:bg-rose-950/10 transition-colors"
                  :disabled="processingCandidateId === cand.id"
                >
                  丢弃拒绝
                </button>
                <button
                  @click="startReviewCandidate(cand)"
                  class="px-4 py-1.5 text-xs bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded hover:opacity-90 flex items-center gap-1"
                  :disabled="processingCandidateId === cand.id"
                >
                  <Check :size="12" />
                  <span>采纳确认...</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
      
    </div>

    <!-- ==================== 采纳候选编辑对话框 Modal ==================== -->
    <div 
      v-if="reviewingCandidate" 
      class="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 p-4 transition-all duration-200"
    >
      <div class="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded max-w-lg w-full p-6 shadow-xl relative animate-in fade-in zoom-in-95 duration-200">
        <button 
          @click="closeReviewCandidate" 
          class="absolute top-4 right-4 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
        >
          <X :size="18" />
        </button>

        <h3 class="text-base font-semibold text-zinc-900 dark:text-zinc-100 flex items-center gap-2">
          <Sparkles :size="18" class="text-amber-500" />
          <span>确认采纳候选偏好</span>
        </h3>
        <p class="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
          将模型学习到的提取规则转换为物理生效的用户画像。在写入前，你可以对提取出的值进行手动校对微调：
        </p>

        <!-- 编辑交互表单 -->
        <div class="mt-5 space-y-4">
          <div>
            <label class="block text-xs font-semibold text-zinc-400 dark:text-zinc-500 mb-1 uppercase">槽位 (Slot Key)</label>
            <div class="text-xs font-mono font-bold bg-zinc-100 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 px-3 py-2 rounded">
              {{ reviewingCandidate.suggested_slot_key }}
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-zinc-400 dark:text-zinc-500 mb-1 uppercase">拟写入的值 (Verified Value)</label>
            <!-- 若目标是枚举类型，提供下拉菜单 -->
            <select 
              v-if="defaultSlots.find((s) => s.key === reviewingCandidate!.suggested_slot_key)?.valType === 'enum'" 
              v-model="candidateEditValue"
              class="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-xs rounded px-3 py-2 text-zinc-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-400"
            >
              <option 
                v-for="opt in defaultSlots.find((s) => s.key === reviewingCandidate!.suggested_slot_key)?.options" 
                :key="opt" 
                :value="opt"
              >
                {{ opt }}
              </option>
            </select>
            <!-- 若目标是布尔类型 -->
            <select 
              v-else-if="defaultSlots.find((s) => s.key === reviewingCandidate!.suggested_slot_key)?.valType === 'boolean'" 
              v-model="candidateEditValue"
              class="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-xs rounded px-3 py-2 text-zinc-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-400"
            >
              <option :value="true">是 (True)</option>
              <option :value="false">否 (False)</option>
            </select>
            <!-- 其他普通文本类型 -->
            <input 
              v-else 
              type="text" 
              v-model="candidateEditValue"
              class="w-full bg-zinc-50 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 text-xs rounded px-3 py-2 text-zinc-800 dark:text-zinc-100 focus:outline-none focus:ring-1 focus:ring-zinc-400"
            />
          </div>

          <div>
            <label class="block text-xs font-semibold text-zinc-400 dark:text-zinc-500 mb-1 uppercase">提取依据背景 (Context Reference)</label>
            <div class="text-xs italic bg-zinc-50 dark:bg-zinc-950/40 p-3 rounded border border-zinc-100 dark:border-zinc-800/40 leading-relaxed text-zinc-500 dark:text-zinc-400 max-h-24 overflow-y-auto">
              "{{ reviewingCandidate.candidate_text }}"
            </div>
          </div>
        </div>

        <!-- 模态框操作栏 -->
        <div class="mt-6 flex items-center justify-end gap-2 pt-4 border-t border-zinc-100 dark:border-zinc-800">
          <button 
            @click="closeReviewCandidate" 
            class="px-4 py-2 text-xs text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded transition-colors"
          >
            取消
          </button>
          <button 
            @click="acceptPref(reviewingCandidate.id)" 
            class="px-4 py-2 text-xs bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded hover:opacity-90 flex items-center gap-1.5 transition-opacity"
            :disabled="processingCandidateId === reviewingCandidate.id"
          >
            <Check :size="13" />
            <span>{{ processingCandidateId === reviewingCandidate.id ? '同步生效中...' : '审核通过并同步' }}</span>
          </button>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
/* 精美的锌灰极简微过渡 */
.fade-in {
  animation: fadeIn 0.2s ease-out;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}
</style>
