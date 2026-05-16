<script setup lang="ts">
/**
 * Skills 只读管理页面
 *
 * 左侧：所有已注册 Skill 列表（来自 SkillRegistry）
 * 右侧：选中 Skill 的详情卡片 + "测试一下"区域
 *
 * 注意：Skill 是代码工程定义，不可在 UI 创建/删除/修改，
 * 这里仅用于让用户"看见"系统具备哪些能力，并能快速验证。
 */
import { onMounted, ref } from 'vue'
import { ChevronRight, Loader2, Play, Sparkles, Wrench, Zap } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import type { SkillInfo, SkillTestResult } from '@/api/skill'
import * as skillApi from '@/api/skill'
import { useKnowledgeStore } from '@/stores/knowledge'

const kb = useKnowledgeStore()

const skills = ref<SkillInfo[]>([])
const loading = ref(false)
const activeName = ref<string | null>(null)
const activeSkill = ref<SkillInfo | null>(null)

// 测试区状态
const testInput = ref('')
const testKbId = ref<number | null>(null)  // document_summarizer 等需要传 kb
const testing = ref(false)
const testResult = ref<SkillTestResult | null>(null)

// 每个 Skill 的"快速示例输入"，让用户一键试用
const SAMPLE_INPUT: Record<string, string> = {
  travel_planner: '我想去成都旅行 3 天，帮我规划一下',
  data_analyst: '帮我算一下 (1 + 2 + 3 + 4 + 5) * 100',
  document_summarizer: '总结一下这个知识库的核心架构',
  research_assistant: '调研一下 LangGraph 的并发执行机制',
  email_drafter: '帮我跟老板请明天的假，理由是去看牙医',
}

// 哪些 Skill 需要选择知识库（rag_search 在 required_tools 里就需要）
function needsKb(skill: SkillInfo | null): boolean {
  if (!skill) return false
  return skill.required_tools.includes('rag_search')
}

onMounted(async () => {
  // 并行加载 Skills 和 KB 列表
  await Promise.all([fetchSkills(), kb.fetchKnowledgeBases()])
  if (skills.value.length > 0) {
    selectSkill(skills.value[0].name)
  }
  // 默认选第一个 KB
  if (kb.knowledgeBases.length > 0 && testKbId.value === null) {
    testKbId.value = kb.knowledgeBases[0].id
  }
})

async function fetchSkills() {
  loading.value = true
  try {
    skills.value = await skillApi.listSkills()
  } catch (e: any) {
    toast.error(`加载 Skills 失败: ${e?.message ?? '未知错误'}`)
  } finally {
    loading.value = false
  }
}

function selectSkill(name: string) {
  activeName.value = name
  activeSkill.value = skills.value.find((s) => s.name === name) ?? null
  testResult.value = null
  // 自动填入示例输入
  testInput.value = SAMPLE_INPUT[name] ?? ''
}

async function handleTest() {
  if (!activeSkill.value || !testInput.value.trim()) {
    toast.error('请输入测试内容')
    return
  }
  if (needsKb(activeSkill.value) && !testKbId.value) {
    toast.error('该 Skill 需要先选择一个知识库')
    return
  }
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await skillApi.testSkill(
      activeSkill.value.name,
      testInput.value.trim(),
      needsKb(activeSkill.value) ? testKbId.value : undefined,
    )
    toast.success('Skill 执行完成')
  } catch (e: any) {
    toast.error(`执行失败: ${e?.message ?? '未知错误'}`)
  } finally {
    testing.value = false
  }
}
</script>

<template>
  <div class="flex h-full">
    <!-- 左侧：Skill 列表 -->
    <div class="w-80 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col">
      <div class="p-4 border-b border-gray-200 dark:border-gray-800">
        <h2 class="text-sm font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-1.5">
          <Sparkles :size="16" class="text-primary-600 dark:text-primary-400" />
          已注册 Skills
        </h2>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
          {{ skills.length }} 个工程编排的能力包
        </p>
      </div>

      <div class="flex-1 overflow-y-auto p-2 space-y-1">
        <div v-if="loading" class="text-center text-sm text-gray-400 dark:text-gray-500 py-8">
          加载中...
        </div>
        <div v-else-if="skills.length === 0" class="text-center text-sm text-gray-400 dark:text-gray-500 py-8">
          暂无已注册 Skill
        </div>

        <div
          v-for="s in skills"
          :key="s.name"
          class="p-3 rounded-lg cursor-pointer transition-colors group"
          :class="activeName === s.name
            ? 'bg-primary-100 dark:bg-primary-900/40'
            : 'hover:bg-gray-100 dark:hover:bg-gray-800'"
          @click="selectSkill(s.name)"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="font-mono text-sm font-semibold text-gray-800 dark:text-gray-100 truncate">
                {{ s.name }}
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 line-clamp-2">
                {{ s.description }}
              </div>
              <div class="flex items-center gap-1 mt-2 text-xs text-gray-400 dark:text-gray-500">
                <Wrench :size="11" />
                <span>{{ s.required_tools.length }} tools</span>
              </div>
            </div>
            <ChevronRight :size="14" class="text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 mt-1" />
          </div>
        </div>
      </div>

      <!-- 说明文字 -->
      <div class="p-3 border-t border-gray-200 dark:border-gray-800 bg-gray-100/50 dark:bg-gray-900/50">
        <p class="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
          💡 Skill 是<b>代码层</b>编排：多个 Tool + Prompt + LLM 调用。每次后端启动时从代码自动注册。
        </p>
      </div>
    </div>

    <!-- 右侧：详情区 -->
    <div class="flex-1 flex flex-col bg-white dark:bg-gray-950">
      <div v-if="!activeSkill" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
        请选择一个 Skill 查看详情
      </div>

      <template v-else>
        <!-- 头部 -->
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <h2 class="text-lg font-mono font-semibold text-gray-800 dark:text-gray-100">{{ activeSkill.name }}</h2>
          <p class="text-sm text-gray-600 dark:text-gray-300 mt-1">{{ activeSkill.description }}</p>
        </div>

        <!-- 元数据区 -->
        <div class="px-6 py-4 space-y-4 border-b border-gray-200 dark:border-gray-800">
          <!-- 依赖 Tools -->
          <div>
            <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1">
              <Wrench :size="12" />
              <span>依赖的 Tools ({{ activeSkill.required_tools.length }})</span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="t in activeSkill.required_tools"
                :key="t"
                class="px-2 py-0.5 text-xs font-mono bg-purple-100 dark:bg-purple-900/40 text-purple-700 dark:text-purple-300 rounded"
              >
                {{ t }}
              </span>
              <span v-if="activeSkill.required_tools.length === 0" class="text-xs text-gray-400 dark:text-gray-500">
                无（仅靠 LLM）
              </span>
            </div>
          </div>

          <!-- 触发关键词 -->
          <div>
            <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1">
              <Zap :size="12" />
              <span>触发关键词（Router 用其做 LLM-free 快速路由）</span>
            </div>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="kw in activeSkill.trigger_keywords"
                :key="kw"
                class="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 rounded"
              >
                {{ kw }}
              </span>
              <span v-if="activeSkill.trigger_keywords.length === 0" class="text-xs text-gray-400 dark:text-gray-500">
                无（只能 LLM 决策路由）
              </span>
            </div>
          </div>
        </div>

        <!-- 测试区 -->
        <div class="flex-1 overflow-y-auto px-6 py-4">
          <div class="text-xs font-semibold text-gray-500 dark:text-gray-400 mb-2 flex items-center gap-1">
            <Play :size="12" />
            <span>测试一下（直接执行该 Skill，不经过 Router）</span>
          </div>

          <!-- 需要 KB 时显示知识库选择器 -->
          <div v-if="needsKb(activeSkill)" class="mb-2">
            <label class="block text-xs text-gray-500 dark:text-gray-400 mb-1">选择知识库（该 Skill 需要）</label>
            <select
              v-model="testKbId"
              class="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              <option :value="null" disabled>请选择...</option>
              <option v-for="k in kb.knowledgeBases" :key="k.id" :value="k.id">
                {{ k.name }}（{{ k.document_count }} 个文档）
              </option>
            </select>
          </div>

          <div class="flex gap-2">
            <input
              v-model="testInput"
              type="text"
              placeholder="输入示例问题..."
              class="flex-1 px-3 py-2 text-sm bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 placeholder:text-gray-400 dark:placeholder:text-gray-500"
              :disabled="testing"
              @keydown.enter="handleTest"
            />
            <button
              class="px-4 py-2 text-sm font-medium bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-1.5"
              :disabled="testing || !testInput.trim()"
              @click="handleTest"
            >
              <Loader2 v-if="testing" :size="14" class="animate-spin" />
              <Play v-else :size="14" />
              <span>{{ testing ? '执行中...' : '执行' }}</span>
            </button>
          </div>

          <!-- 测试结果 -->
          <div v-if="testResult" class="mt-4 space-y-3">
            <!-- 回答 -->
            <div class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <div class="px-3 py-2 bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                Skill 回复
              </div>
              <div class="px-3 py-3 text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap leading-relaxed">
                {{ testResult.answer }}
              </div>
            </div>

            <!-- Tool 调用记录 -->
            <div v-if="testResult.tool_calls.length > 0" class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <div class="px-3 py-2 bg-gray-50 dark:bg-gray-800 text-xs font-semibold text-gray-600 dark:text-gray-300 border-b border-gray-200 dark:border-gray-700">
                Tool 调用链路 ({{ testResult.tool_calls.length }} 次)
              </div>
              <div class="divide-y divide-gray-100 dark:divide-gray-800">
                <details
                  v-for="(tc, i) in testResult.tool_calls"
                  :key="i"
                  class="text-xs"
                >
                  <summary class="px-3 py-2 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800/50 flex items-center justify-between">
                    <span class="font-mono font-semibold text-purple-700 dark:text-purple-300">{{ tc.name }}</span>
                    <span class="text-gray-400 dark:text-gray-500">{{ tc.kind ?? 'tool' }}</span>
                  </summary>
                  <pre class="px-3 pb-3 pt-1 text-xs text-gray-700 dark:text-gray-300 overflow-x-auto whitespace-pre-wrap bg-gray-50/50 dark:bg-gray-900/50">{{ JSON.stringify({ arguments: tc.arguments, result: tc.result }, null, 2) }}</pre>
                </details>
              </div>
            </div>

            <!-- meta 信息（如有）-->
            <details v-if="testResult.meta && Object.keys(testResult.meta).length" class="text-xs">
              <summary class="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">
                meta 信息
              </summary>
              <pre class="mt-2 p-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded text-gray-700 dark:text-gray-200 overflow-x-auto">{{ JSON.stringify(testResult.meta, null, 2) }}</pre>
            </details>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
