<script setup lang="ts">
/**
 * Skills 页面 (壳组件)
 *
 * 管理技能列表与测试调用状态。UI 层已被完全拆分为：
 * 1. SkillSidebar.vue
 * 2. SkillDetailHeader.vue
 * 3. SkillTestPanel.vue
 */
import { onMounted, ref, computed } from 'vue'
import { toast } from 'vue-sonner'

import type { SkillInfo, SkillTestResult } from '@/api/skill'
import * as skillApi from '@/api/skill'
import { useKnowledgeStore } from '@/stores/knowledge'

import SkillSidebar from '@/components/skills/SkillSidebar.vue'
import SkillDetailHeader from '@/components/skills/SkillDetailHeader.vue'
import SkillTestPanel from '@/components/skills/SkillTestPanel.vue'

const kb = useKnowledgeStore()

// 全局状态
const skills = ref<SkillInfo[]>([])
const loading = ref(false)
const activeName = ref<string | null>(null)
const activeView = ref<'list' | 'details'>('list')

// 测试区状态
const testInput = ref('')
const testKbId = ref<number | null>(null)
const testing = ref(false)
const testResult = ref<SkillTestResult | null>(null)

const activeSkill = computed(() => skills.value.find((s) => s.name === activeName.value) ?? null)

// 每个 Skill 的"快速示例输入"
const SAMPLE_INPUT: Record<string, string> = {
  travel_planner: '我想去成都旅行 3 天，帮我规划一下',
  data_analyst: '帮我算一下 (1 + 2 + 3 + 4 + 5) * 100',
  document_summarizer: '总结一下这个知识库的核心架构',
  research_assistant: '调研一下 LangGraph 的并发执行机制',
  email_drafter: '帮我跟老板请明天的假，理由是去看牙医',
}

function needsKb(skill: SkillInfo | null): boolean {
  if (!skill) return false
  return skill.required_tools.includes('rag_search')
}

onMounted(async () => {
  await Promise.all([fetchSkills(), kb.fetchKnowledgeBases()])
  if (skills.value.length > 0) {
    selectSkill(skills.value[0].name)
    activeView.value = 'list'
  }
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
  testResult.value = null
  testInput.value = SAMPLE_INPUT[name] ?? ''
  activeView.value = 'details'
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
  <div class="flex h-full bg-white dark:bg-zinc-950 font-sans text-zinc-900 dark:text-zinc-100">
    <!-- 左侧：Skill 列表 -->
    <SkillSidebar 
      :skills="skills"
      :loading="loading"
      :active-name="activeName"
      :active-view="activeView"
      @select="selectSkill"
    />

    <!-- 右侧：详情与测试区 -->
    <div 
      class="flex-grow flex flex-col bg-white dark:bg-zinc-950"
      :class="{'hidden md:flex': activeSkill === null || activeView === 'list'}"
    >
      <div v-if="!activeSkill" class="flex-1 flex items-center justify-center text-zinc-400 dark:text-zinc-500 font-medium tracking-wide">
        请选择一个 Skill 查看详情
      </div>

      <template v-else>
        <!-- 顶部信息 -->
        <SkillDetailHeader 
          :skill="activeSkill"
          @back="activeView = 'list'"
        />

        <!-- 测试控制台面板 -->
        <SkillTestPanel 
          :active-skill="activeSkill"
          :needs-kb="needsKb(activeSkill)"
          :kb-list="kb.knowledgeBases"
          v-model:test-input="testInput"
          v-model:test-kb-id="testKbId"
          :testing="testing"
          :test-result="testResult"
          @test="handleTest"
        />
      </template>
    </div>
  </div>
</template>
