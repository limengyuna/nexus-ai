<script setup lang="ts">
import { computed } from 'vue'
import { Check, Sparkles, Loader2, X, AlertCircle } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'

const chatStore = useChatStore()

const agentNameMap: Record<string, string> = {
  rag_agent: '知识库检索',
  tool_agent: '工具调用',
  business_context_agent: '业务上下文',
  synthesis_agent: '信息整合'
}

function getReadableAgentName(name: string) {
  return agentNameMap[name] || '智能决策'
}

// 当仍有请求在进行，且尚未获取到正文时，保持展开
// 为了柔和的动画，我们通过父组件控制显示与隐藏，此处仅处理内部渲染状态
const plans = computed(() => chatStore.lastTaskPlan || [])

// 判断是否有真实的步骤数据
const hasPlans = computed(() => plans.value.length > 0)

// 动态计算完成步数
const completedCount = computed(() => plans.value.filter(p => p.status === 'success' || p.status === 'completed').length)
</script>

<template>
  <div class="relative w-full overflow-hidden transition-all duration-500 ease-[cubic-bezier(0.23,1,0.32,1)] rounded-2xl border border-zinc-200/60 dark:border-zinc-700/50 bg-white/70 dark:bg-zinc-900/60 backdrop-blur-2xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] dark:shadow-[0_8px_30px_rgb(0,0,0,0.2)] mb-4">
    
    <!-- 顶部动态渐变边框高光 -->
    <div class="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-zinc-400/40 dark:via-zinc-400/20 to-transparent"></div>

    <div class="px-5 py-4">
      <!-- 头部：呼吸指示灯和标题 -->
      <div class="flex items-center gap-3 mb-2">
        <div class="relative flex h-3 w-3">
          <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-zinc-400 dark:bg-zinc-500 opacity-40"></span>
          <span class="relative inline-flex rounded-full h-3 w-3 bg-zinc-600 dark:bg-zinc-400"></span>
        </div>
        <span class="text-sm font-semibold tracking-wide text-zinc-800 dark:text-zinc-200">
          Agent 深度推演中
        </span>
        
        <div v-if="hasPlans" class="ml-auto text-xs font-medium text-zinc-500 dark:text-zinc-400 bg-zinc-100/80 dark:bg-zinc-800/80 px-2 py-0.5 rounded-full">
          {{ completedCount }} / {{ plans.length }} 步
        </div>
      </div>

      <!-- 任务流逝列表 -->
      <div class="mt-4 space-y-3 relative before:absolute before:inset-y-0 before:left-[11px] before:w-[1px] before:bg-gradient-to-b before:from-zinc-300 dark:before:from-zinc-700 before:to-transparent">
        <transition-group 
          name="step-list" 
          tag="div" 
          class="space-y-3"
        >
          <div 
            v-for="(plan, index) in plans" 
            :key="index"
            class="relative flex items-start gap-4"
          >
            <!-- 状态图标 -->
            <div class="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white dark:bg-zinc-900 shadow-sm border border-zinc-200 dark:border-zinc-700"
                 :class="{
                   'ring-2 ring-zinc-100 dark:ring-zinc-800': plan.status === 'pending' || plan.status === 'in_progress',
                   'border-green-500/50 bg-green-50/50 dark:bg-green-950/30': plan.status === 'success' || plan.status === 'completed',
                   'border-red-500/50 bg-red-50/50 dark:bg-red-950/30': plan.status === 'failed',
                   'border-orange-500/50 bg-orange-50/50 dark:bg-orange-950/30': plan.status === 'cancelled'
                 }">
              <Check v-if="plan.status === 'success' || plan.status === 'completed'" class="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
              <Loader2 v-else-if="plan.status === 'pending' || plan.status === 'in_progress'" class="h-3.5 w-3.5 text-zinc-600 dark:text-zinc-400 animate-spin" />
              <X v-else-if="plan.status === 'failed'" class="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
              <AlertCircle v-else-if="plan.status === 'cancelled'" class="h-3.5 w-3.5 text-orange-600 dark:text-orange-400" />
              <Sparkles v-else class="h-3.5 w-3.5 text-zinc-400 dark:text-zinc-500" />
            </div>

            <!-- 任务描述 -->
            <div class="flex flex-col pt-0.5">
              <span class="text-[13px] font-medium leading-relaxed"
                    :class="{
                      'text-zinc-900 dark:text-zinc-100': plan.status === 'pending' || plan.status === 'in_progress',
                      'text-zinc-500 dark:text-zinc-400': plan.status === 'success' || plan.status === 'completed',
                      'text-red-600 dark:text-red-400 line-through': plan.status === 'failed',
                      'text-orange-600 dark:text-orange-400 line-through': plan.status === 'cancelled'
                    }">
                {{ plan.instruction }}
              </span>
              <span class="text-[11px] text-zinc-400 dark:text-zinc-500 font-medium mt-0.5 tracking-wider">
                {{ getReadableAgentName(plan.agent) }}
              </span>
            </div>
          </div>
        </transition-group>
        
        <!-- 骨架占位（当还没有 plan 时显示流光骨架） -->
        <div v-if="!hasPlans" class="relative flex items-start gap-4 opacity-60">
           <div class="relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700">
              <Loader2 class="h-3 w-3 text-zinc-400 animate-spin" />
           </div>
           <div class="flex flex-col gap-2 w-full pt-1.5">
              <div class="h-2 w-3/4 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse"></div>
              <div class="h-2 w-1/4 bg-zinc-200 dark:bg-zinc-800 rounded animate-pulse"></div>
           </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 步骤列表平滑过渡动画 */
.step-list-move,
.step-list-enter-active,
.step-list-leave-active {
  transition: all 0.5s cubic-bezier(0.23, 1, 0.32, 1);
}
.step-list-enter-from {
  opacity: 0;
  transform: translateY(-10px) scale(0.98);
}
.step-list-leave-to {
  opacity: 0;
  transform: translateY(10px) scale(0.95);
  position: absolute;
}
</style>
