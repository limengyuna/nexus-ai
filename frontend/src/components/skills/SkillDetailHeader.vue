<script setup lang="ts">
import { Wrench, Zap } from 'lucide-vue-next'
import type { SkillInfo } from '@/api/skill'

defineProps<{
  skill: SkillInfo
}>()

defineEmits<{
  (e: 'back'): void
}>()
</script>

<template>
  <div>
    <!-- 头部：标题与描述 -->
    <div class="px-8 py-6 border-b border-zinc-200/80 dark:border-zinc-800/60 bg-white/50 dark:bg-zinc-950/50 backdrop-blur-sm">
      <button
        @click="$emit('back')"
        class="md:hidden mb-5 flex items-center gap-1.5 text-xs font-medium text-zinc-600 dark:text-zinc-400 border border-zinc-200 dark:border-zinc-800 rounded-lg px-3 py-1.5 self-start active:scale-95 transition-all bg-white dark:bg-zinc-900 shadow-sm"
      >
        ← 返回技能列表
      </button>
      
      <div class="flex items-center gap-3 mb-2">
        <h2 class="text-2xl font-mono font-bold text-zinc-900 dark:text-zinc-50 tracking-tight">{{ skill.name }}</h2>
      </div>
      <p class="text-[15px] text-zinc-600 dark:text-zinc-400 leading-relaxed max-w-3xl">{{ skill.description }}</p>
    </div>

    <!-- 元数据区：胶囊标签 -->
    <div class="px-8 py-6 space-y-6 border-b border-zinc-200/80 dark:border-zinc-800/60 bg-zinc-50/30 dark:bg-zinc-900/20">
      <!-- 依赖 Tools -->
      <div>
        <div class="text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-3 flex items-center gap-1.5">
          <Wrench :size="13" class="text-indigo-500" />
          <span>依赖的 Tools ({{ skill.required_tools.length }})</span>
        </div>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="t in skill.required_tools"
            :key="t"
            class="px-3 py-1 text-xs font-mono font-semibold bg-indigo-50 dark:bg-indigo-500/10 text-indigo-700 dark:text-indigo-300 border border-indigo-100 dark:border-indigo-500/20 rounded-full shadow-sm"
          >
            {{ t }}
          </span>
          <span v-if="skill.required_tools.length === 0" class="text-xs font-medium text-zinc-400 dark:text-zinc-500 italic">
            无（仅靠 LLM 自治）
          </span>
        </div>
      </div>

      <!-- 触发关键词 -->
      <div>
        <div class="text-xs font-bold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 mb-3 flex items-center gap-1.5">
          <Zap :size="13" class="text-amber-500" />
          <span>触发关键词 <span class="text-[10px] font-normal lowercase tracking-normal text-zinc-400">(Router LLM-free 快速路由)</span></span>
        </div>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="kw in skill.trigger_keywords"
            :key="kw"
            class="px-3 py-1 text-xs font-medium bg-amber-50 dark:bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-100 dark:border-amber-500/20 rounded-full shadow-sm"
          >
            {{ kw }}
          </span>
          <span v-if="skill.trigger_keywords.length === 0" class="text-xs font-medium text-zinc-400 dark:text-zinc-500 italic">
            无（只能依赖 LLM 决策路由）
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
