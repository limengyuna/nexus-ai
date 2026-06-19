<script setup lang="ts">
/**
 * 记忆管理页面 (MemoryView.vue) - 重构版壳组件
 *
 * 全面重构为三 Tab 联动记忆管理面板，内部逻辑已拆解为：
 * 1. MemoryFactsTab (长期记忆事实)
 * 2. MemoryProfileTab (结构化用户档案)
 * 3. MemoryCandidatesTab (偏好审核候选区)
 */
import { onMounted, ref } from 'vue'
import { Brain, RefreshCw } from 'lucide-vue-next'
import { useMemoryStore } from '@/stores/memory'
import { defaultSlots } from '@/constants/memory'

// 引入拆分后的子组件
import MemoryFactsTab from '@/components/memory/MemoryFactsTab.vue'
import MemoryProfileTab from '@/components/memory/MemoryProfileTab.vue'
import MemoryCandidatesTab from '@/components/memory/MemoryCandidatesTab.vue'

const memory = useMemoryStore()

// 当前激活的面板
const activeTab = ref<'facts' | 'profile' | 'candidates'>('facts')

onMounted(() => {
  loadData()
})

function loadData() {
  if (activeTab.value === 'facts') {
    // facts 内部自己有 scope 状态，但全局刷新通常恢复默认或保留。
    // 这里调用无参相当于只刷新默认作用域或全部，在组件内部 scopeFilter 控制更为严谨，
    // 但粗粒度重新 fetch 一下作为全局刷新也没问题。
    memory.fetchFacts()
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
</script>

<template>
  <div class="h-full flex flex-col bg-zinc-50 dark:bg-zinc-950 font-sans">
    <!-- 顶部高端工业风标题栏（去线框） -->
    <header class="flex-shrink-0 bg-white dark:bg-zinc-900 px-4 md:px-8 py-5 md:py-6 shadow-xs">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
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
          class="flex items-center justify-center gap-2 px-3 py-2 text-sm text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded transition-colors duration-200 border border-zinc-200 dark:border-zinc-800 self-start sm:self-center"
        >
          <RefreshCw :size="15" :stroke-width="2" />
          <span>刷新数据</span>
        </button>
      </div>

      <!-- Tab 导航栏（去除横贯全屏的底线，采用现代悬浮胶囊感） -->
      <div class="flex flex-wrap items-center gap-2 mt-6">
        <button
          @click="switchTab('facts')"
          class="relative px-3.5 py-1.5 text-xs font-semibold transition-all duration-200 rounded-md"
          :class="activeTab === 'facts' 
            ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 shadow-xs' 
            : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50'"
        >
          长期记忆事实 (L2 Facts)
        </button>
        <button
          @click="switchTab('profile')"
          class="relative px-3.5 py-1.5 text-xs font-semibold transition-all duration-200 rounded-md flex items-center gap-1.5"
          :class="activeTab === 'profile' 
            ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 shadow-xs' 
            : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50'"
        >
          结构化用户档案 (Profile Slots)
          <span class="px-1.5 py-0.5 text-[9px] rounded-full bg-white dark:bg-zinc-900 shadow-xs text-zinc-500 font-mono">
            {{ memory.profileValues.length }}/{{ defaultSlots.length }}
          </span>
        </button>
        <button
          @click="switchTab('candidates')"
          class="relative px-3.5 py-1.5 text-xs font-semibold transition-all duration-200 rounded-md flex items-center gap-1.5"
          :class="activeTab === 'candidates' 
            ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 shadow-xs' 
            : 'text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-300 hover:bg-zinc-50 dark:hover:bg-zinc-800/50'"
        >
          偏好审核候选区 (Candidates)
          <span 
            v-if="memory.candidates.length > 0" 
            class="px-1.5 py-0.5 text-[9px] rounded-full bg-rose-100 dark:bg-rose-900 text-rose-600 dark:text-rose-300 shadow-xs font-bold font-mono animate-pulse"
          >
            {{ memory.candidates.length }} 待审
          </span>
        </button>
      </div>
    </header>

    <!-- 主展示区：使用子组件渲染 -->
    <div class="flex-1 overflow-y-auto px-4 md:px-8 py-5 md:py-6 relative">
      <!-- 增加淡入淡出过渡 -->
      <transition name="fade" mode="out-in">
        <KeepAlive>
          <component :is="activeTab === 'facts' ? MemoryFactsTab : (activeTab === 'profile' ? MemoryProfileTab : MemoryCandidatesTab)" />
        </KeepAlive>
      </transition>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
