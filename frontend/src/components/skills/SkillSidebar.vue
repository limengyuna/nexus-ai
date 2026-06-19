<script setup lang="ts">
import { ChevronRight, Sparkles, Wrench } from 'lucide-vue-next'
import type { SkillInfo } from '@/api/skill'

const props = defineProps<{
  skills: SkillInfo[]
  loading: boolean
  activeName: string | null
  activeView: 'list' | 'details'
}>()

const emit = defineEmits<{
  (e: 'select', name: string): void
}>()
</script>

<template>
  <div 
    class="w-full md:w-80 bg-zinc-50/50 dark:bg-zinc-900/40 border-r border-zinc-200/80 dark:border-zinc-800/60 flex flex-col flex-shrink-0"
    :class="{'hidden md:flex': activeName !== null && activeView === 'details'}"
  >
    <div class="p-5 border-b border-zinc-200/80 dark:border-zinc-800/60 bg-white/50 dark:bg-zinc-950/50 backdrop-blur-sm">
      <h2 class="text-[15px] font-bold text-zinc-800 dark:text-zinc-100 flex items-center gap-2">
        <Sparkles :size="16" class="text-primary-500 dark:text-primary-400" />
        已注册 Skills
      </h2>
      <p class="text-xs text-zinc-500 dark:text-zinc-400 mt-1.5 font-medium">
        {{ skills.length }} 个工程编排的能力包
      </p>
    </div>

    <div class="flex-1 overflow-y-auto px-3 py-3 space-y-2">
      <div v-if="loading" class="text-center text-sm text-zinc-400 dark:text-zinc-500 py-12 flex flex-col items-center gap-2">
        <div class="w-5 h-5 rounded-full border-2 border-primary-500 border-t-transparent animate-spin"></div>
        <span>加载中...</span>
      </div>
      
      <div v-else-if="skills.length === 0" class="text-center text-sm text-zinc-400 dark:text-zinc-500 py-12">
        暂无已注册 Skill
      </div>

      <div
        v-for="s in skills"
        :key="s.name"
        class="group p-4 rounded-2xl cursor-pointer transition-all duration-300 relative overflow-hidden"
        :class="activeName === s.name
          ? 'bg-white dark:bg-zinc-800/80 shadow-[0_2px_10px_-4px_rgba(0,0,0,0.1)] dark:shadow-[0_4px_20px_-4px_rgba(0,0,0,0.4)] ring-1 ring-zinc-200 dark:ring-zinc-700/50'
          : 'hover:bg-white/60 dark:hover:bg-zinc-800/40 border border-transparent'"
        @click="$emit('select', s.name)"
      >
        <!-- 侧边指示条 (激活时显示) -->
        <div 
          class="absolute left-0 top-0 bottom-0 w-1 bg-primary-500 transition-transform duration-300 origin-left"
          :class="activeName === s.name ? 'scale-x-100' : 'scale-x-0'"
        ></div>

        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <div class="font-mono text-sm font-bold text-zinc-800 dark:text-zinc-100 truncate flex items-center gap-2">
              {{ s.name }}
            </div>
            <div class="text-xs text-zinc-500 dark:text-zinc-400 mt-1.5 leading-relaxed line-clamp-2">
              {{ s.description }}
            </div>
            <div class="flex items-center gap-1.5 mt-3 text-[10px] font-medium uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
              <div class="flex items-center gap-1 px-1.5 py-0.5 rounded-sm bg-zinc-100 dark:bg-zinc-900">
                <Wrench :size="10" />
                <span>{{ s.required_tools.length }} tools</span>
              </div>
            </div>
          </div>
          <ChevronRight 
            :size="16" 
            class="text-zinc-400 transition-all duration-300 flex-shrink-0 mt-1" 
            :class="activeName === s.name ? 'opacity-100 translate-x-0 text-primary-500' : 'opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0'" 
          />
        </div>
      </div>
    </div>

    <!-- 说明文字 -->
    <div class="p-4 border-t border-zinc-200/80 dark:border-zinc-800/60 bg-gradient-to-b from-transparent to-zinc-100/50 dark:to-zinc-900/50">
      <div class="flex items-start gap-2 bg-white/60 dark:bg-zinc-900/80 p-3 rounded-xl border border-zinc-200/50 dark:border-zinc-800/50 shadow-sm">
        <span class="text-lg leading-none">💡</span>
        <p class="text-[11px] text-zinc-500 dark:text-zinc-400 leading-relaxed font-medium">
          Skill 是<b>代码层</b>编排：多个 Tool + Prompt + LLM 调用。每次后端启动时从代码自动注册。
        </p>
      </div>
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
