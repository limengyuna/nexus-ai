<script setup lang="ts">
/**
 * 应用主布局：左侧导航 + 右侧内容
 */
import { onMounted, markRaw, ref } from 'vue'
import { RouterLink, RouterView, useRoute, useRouter } from 'vue-router'
import { Brain, Library, MessageSquare, Moon, Plug, Sparkles, Sun, type LucideIcon } from 'lucide-vue-next'

import { useAuthStore } from '@/stores/auth'
import { useTheme } from '@/composables/useTheme'

const { theme, toggle: toggleTheme } = useTheme()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// 侧栏 hover 展开状态。默认收起为 64px，hover 后浮层展开为 208px，不挤压主内容
const hovered = ref(false)

// 连点5下 logo 进入隐藏的面试复盘页面
let logoClickCount = 0
let logoClickTimer: ReturnType<typeof setTimeout> | null = null
function handleLogoClick() {
  logoClickCount++
  if (logoClickTimer) clearTimeout(logoClickTimer)
  if (logoClickCount >= 5) {
    logoClickCount = 0
    router.push('/interview')
    return
  }
  // 2秒内未达到5次则重置计数
  logoClickTimer = setTimeout(() => { logoClickCount = 0 }, 2000)
}

onMounted(async () => {
  if (!auth.userInfo) {
    try {
      await auth.fetchUserInfo()
    } catch {
      // 401 已被拦截器统一处理
    }
  }
})

function logout() {
  auth.logout()
  router.push('/login')
}

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
}

// markRaw 避免 Vue 把 Lucide 组件做成响应式（图标组件无需响应化，提升性能）
const navItems: NavItem[] = [
  { to: '/chat', label: '智能对话', icon: markRaw(MessageSquare) },
  { to: '/knowledge', label: '知识库', icon: markRaw(Library) },
  { to: '/skills', label: 'Skills', icon: markRaw(Sparkles) },
  { to: '/mcp', label: 'MCP 配置', icon: markRaw(Plug) },
  { to: '/memory', label: '长期记忆', icon: markRaw(Brain) },
]
</script>

<template>
  <div class="flex h-screen bg-[#f8fafc] dark:bg-[#07080d] relative font-outfit">
    <!-- 64px 占位（不变形），保证主区域始终从 x=64 开始 -->
    <div class="w-16 flex-shrink-0"></div>

    <!-- 真正的侧栏：absolute 浮层，使用半透明磨砂玻璃设计，支持平滑弹性展开 -->
    <aside
      class="absolute top-0 left-0 h-screen bg-white/80 dark:bg-[#0c0d14]/80 backdrop-blur-xl border-r border-gray-200/50 dark:border-gray-800/40 flex flex-col z-40 transition-all duration-300 cubic-bezier(0.16, 1, 0.3, 1) overflow-hidden"
      :class="hovered ? 'w-52 shadow-[0_8px_32px_rgba(99,102,241,0.03)] dark:shadow-[0_8px_32px_rgba(0,0,0,0.3)]' : 'w-16'"
      @mouseenter="hovered = true"
      @mouseleave="hovered = false"
    >
      <!-- 品牌区 -->
      <div class="h-16 flex items-center px-3 border-b border-gray-100/60 dark:border-gray-800/40 flex-shrink-0">
        <div
          class="w-10 h-10 rounded-xl bg-gradient-to-br from-[#faf9f6]/95 to-[#eae4dc]/95 dark:from-gray-800/90 dark:to-gray-900/90 border border-white/80 dark:border-white/5 shadow-[inset_0_1.5px_2.5px_rgba(255,255,255,0.7),0_4px_12px_rgba(200,179,160,0.08)] dark:shadow-[inset_0_1px_1px_rgba(255,255,255,0.1),0_4px_12px_rgba(0,0,0,0.3)] flex items-center justify-center flex-shrink-0 cursor-pointer select-none active:scale-95 transition-all duration-300 hover:scale-[1.05] hover:rotate-6"
          @click="handleLogoClick"
        >
          <svg viewBox="0 0 24 24" fill="none" class="w-5.5 h-5.5 flex-shrink-0" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="logo-sand-grad-sidebar" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#e3d5ca" />
                <stop offset="50%" stop-color="#c8b3a0" />
                <stop offset="100%" stop-color="#9c8470" />
              </linearGradient>
              <linearGradient id="logo-charcoal-grad-sidebar" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#8c92ac" />
                <stop offset="100%" stop-color="#4b526d" />
              </linearGradient>
            </defs>
            <path d="M6 17C6 11 8 7 11 7s5 3 5 8-2 6-5 6" stroke="url(#logo-sand-grad-sidebar)" stroke-width="2.5" stroke-linecap="round" />
            <path d="M18 7C18 13 16 17 13 17s-5-3-5-8 2-6 5-6" stroke="url(#logo-charcoal-grad-sidebar)" stroke-width="2.5" stroke-linecap="round" style="mix-blend-mode: multiply; opacity: 0.95;" />
          </svg>
        </div>
        <span
          class="ml-3 text-sm font-bold bg-gradient-to-r from-gray-800 to-gray-600 dark:from-gray-100 dark:to-gray-300 bg-clip-text text-transparent whitespace-nowrap transition-opacity duration-200"
          :class="hovered ? 'opacity-100' : 'opacity-0'"
        >
          NexusAI
        </span>
      </div>

      <!-- 图标导航 -->
      <nav class="flex-1 py-4 space-y-1.5 px-2">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item-btn relative flex items-center h-11 px-2 rounded-xl transition-all duration-200 overflow-hidden"
          :class="route.path.startsWith(item.to)
            ? 'bg-primary-50/80 dark:bg-primary-950/30 border border-primary-100/40 dark:border-primary-900/30 text-primary-600 dark:text-primary-400 shadow-sm'
            : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100/60 dark:hover:bg-gray-800/40 hover:text-gray-700 dark:hover:text-gray-200 border border-transparent'"
        >
          <!-- 激活态流光左侧指示条 -->
          <div 
            v-if="route.path.startsWith(item.to)" 
            class="absolute left-0 top-3 bottom-3 w-1 bg-gradient-to-b from-[#c8b3a0] to-[#bda590] rounded-r-md"
          ></div>

          <!-- 图标容器 -->
          <div class="w-12 h-11 flex items-center justify-center flex-shrink-0">
            <component 
              :is="item.icon" 
              :size="18" 
              :stroke-width="2" 
              class="transition-all duration-300"
              :class="[
                item.to === '/chat' ? 'icon-chat' : '',
                item.to === '/knowledge' ? 'icon-kb' : '',
                item.to === '/skills' ? 'icon-sparkles' : '',
                item.to === '/mcp' ? 'icon-plug' : '',
                item.to === '/memory' ? 'icon-brain' : ''
              ]"
            />
          </div>
          <!-- 文字标签 -->
          <span
            class="text-xs font-semibold whitespace-nowrap transition-opacity duration-200"
            :class="hovered ? 'opacity-100' : 'opacity-0'"
          >
            {{ item.label }}
          </span>
        </RouterLink>
      </nav>

      <!-- 主题切换按钮 -->
      <div class="px-2 pb-1.5 flex-shrink-0">
        <button
          class="flex items-center w-full h-11 px-2 rounded-xl text-gray-500 dark:text-gray-400 hover:bg-gray-100/60 dark:hover:bg-gray-800/40 hover:text-gray-700 dark:hover:text-gray-200 border border-transparent transition-all duration-200 overflow-hidden"
          :title="theme === 'dark' ? '切换到浅色模式' : '切换到暗色模式'"
          @click="toggleTheme"
        >
          <div class="w-12 h-11 flex items-center justify-center flex-shrink-0">
            <Sun v-if="theme === 'dark'" :size="18" :stroke-width="2" class="text-amber-500 hover:rotate-45 transition-transform duration-300" />
            <Moon v-else :size="18" :stroke-width="2" class="text-gray-600 dark:text-gray-300 hover:-rotate-12 transition-transform duration-300" />
          </div>
          <span
            class="text-xs font-semibold whitespace-nowrap transition-opacity duration-200"
            :class="hovered ? 'opacity-100' : 'opacity-0'"
          >
            {{ theme === 'dark' ? '浅色模式' : '暗色模式' }}
          </span>
        </button>
      </div>

      <!-- 底部用户区 -->
      <div class="p-2 border-t border-gray-100/60 dark:border-gray-800/40 flex-shrink-0">
        <button
          class="flex items-center w-full h-11 px-2 rounded-xl hover:bg-gray-100/60 dark:hover:bg-gray-800/40 border border-transparent hover:border-gray-200/30 dark:hover:border-gray-800/30 transition-all duration-200 overflow-hidden"
          @click="logout"
        >
          <div class="w-12 h-11 flex items-center justify-center flex-shrink-0">
            <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-gray-800/10 to-gray-700/10 dark:from-gray-800/20 dark:to-gray-700/20 text-gray-700 dark:text-gray-300 border border-gray-500/10 flex items-center justify-center text-xs font-bold shadow-inner">
              {{ (auth.userInfo?.username ?? '?').charAt(0).toUpperCase() }}
            </div>
          </div>
          <div
            class="flex flex-col items-start min-w-0 transition-opacity duration-200"
            :class="hovered ? 'opacity-100' : 'opacity-0'"
          >
            <span class="text-xs font-bold text-gray-700 dark:text-gray-200 truncate w-full text-left">
              {{ auth.userInfo?.username ?? '未登录' }}
            </span>
            <span class="text-[9px] text-gray-400 dark:text-gray-500 font-medium tracking-wide">安全登出</span>
          </div>
        </button>
      </div>
    </aside>

    <!-- 主区域 -->
    <main class="flex-1 overflow-hidden relative z-10">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
/* 导航图标专有的 hover 炫彩微交互 */
.nav-item-btn:hover .icon-chat {
  transform: scale(1.12) rotate(-5deg);
  color: #9c8470;
}
.dark .nav-item-btn:hover .icon-chat {
  color: #c8b3a0;
}

.nav-item-btn:hover .icon-kb {
  transform: translateY(-2px) scale(1.05);
  color: #2563eb;
}
.dark .nav-item-btn:hover .icon-kb {
  color: #60a5fa;
}

.nav-item-btn:hover .icon-sparkles {
  animation: sparkles-spin 1.2s cubic-bezier(0.25, 1, 0.5, 1) infinite;
  color: #d97706;
}
.dark .nav-item-btn:hover .icon-sparkles {
  color: #fbbf24;
}

.nav-item-btn:hover .icon-plug {
  animation: plug-swing 0.6s ease-in-out infinite alternate;
  color: #10b981;
}
.dark .nav-item-btn:hover .icon-plug {
  color: #34d399;
}

.nav-item-btn:hover .icon-brain {
  animation: brain-pulse 1.4s ease-in-out infinite;
  color: #db2777;
}
.dark .nav-item-btn:hover .icon-brain {
  color: #f472b6;
}

/* 图标动画关键帧 */
@keyframes sparkles-spin {
  0% { transform: scale(1) rotate(0deg); }
  50% { transform: scale(1.2) rotate(180deg); }
  100% { transform: scale(1) rotate(360deg); }
}

@keyframes plug-swing {
  0% { transform: rotate(-10deg) scale(1.05); }
  100% { transform: rotate(10deg) scale(1.05); }
}

@keyframes brain-pulse {
  0% { transform: scale(1); filter: drop-shadow(0 0 0 rgba(219, 39, 119, 0)); }
  50% { transform: scale(1.15); filter: drop-shadow(0 0 4px rgba(219, 39, 119, 0.4)); }
  100% { transform: scale(1); filter: drop-shadow(0 0 0 rgba(219, 39, 119, 0)); }
}
</style>
