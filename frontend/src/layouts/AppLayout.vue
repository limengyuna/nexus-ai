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
  <div class="flex h-screen bg-gray-50 dark:bg-gray-950 relative">
    <!-- 64px 占位（不变形），保证主区域始终从 x=64 开始 -->
    <div class="w-16 flex-shrink-0"></div>

    <!-- 真正的侧栏：absolute 浮层，hover 时从 64px 平滑展开到 208px 显示文字 -->
    <aside
      class="absolute top-0 left-0 h-screen bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col z-40 transition-all duration-200 ease-out overflow-hidden"
      :class="hovered ? 'w-52 shadow-2xl' : 'w-16'"
      @mouseenter="hovered = true"
      @mouseleave="hovered = false"
    >
      <!-- 品牌区 -->
      <div class="h-16 flex items-center px-3 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
        <div
          class="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-primary-700 text-white flex items-center justify-center font-bold text-base shadow-sm flex-shrink-0 cursor-pointer select-none"
          @click="handleLogoClick"
        >
          N
        </div>
        <span
          class="ml-3 text-base font-semibold text-gray-800 dark:text-gray-100 whitespace-nowrap transition-opacity duration-150"
          :class="hovered ? 'opacity-100' : 'opacity-0'"
        >
          NexusAI
        </span>
      </div>

      <!-- 图标导航 -->
      <nav class="flex-1 py-3 space-y-1 px-2">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="flex items-center h-12 px-2 rounded-xl transition-colors overflow-hidden"
          :class="route.path.startsWith(item.to)
            ? 'bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300'
            : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200'"
        >
          <!-- 图标固定居中 12*4=48px -->
          <div class="w-12 h-12 flex items-center justify-center flex-shrink-0">
            <component :is="item.icon" :size="20" :stroke-width="2" />
          </div>
          <!-- 文字标签 hover 时显示 -->
          <span
            class="text-sm font-medium whitespace-nowrap transition-opacity duration-150"
            :class="hovered ? 'opacity-100' : 'opacity-0'"
          >
            {{ item.label }}
          </span>
        </RouterLink>
      </nav>

      <!-- 主题切换按钮 -->
      <div class="px-2 pb-1 flex-shrink-0">
        <button
          class="flex items-center w-full h-12 px-2 rounded-xl text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-800 hover:text-gray-700 dark:hover:text-gray-200 transition-colors overflow-hidden"
          :title="theme === 'dark' ? '切换到浅色模式' : '切换到暗色模式'"
          @click="toggleTheme"
        >
          <div class="w-12 h-12 flex items-center justify-center flex-shrink-0">
            <Sun v-if="theme === 'dark'" :size="20" :stroke-width="2" />
            <Moon v-else :size="20" :stroke-width="2" />
          </div>
          <span
            class="text-sm font-medium whitespace-nowrap transition-opacity duration-150"
            :class="hovered ? 'opacity-100' : 'opacity-0'"
          >
            {{ theme === 'dark' ? '浅色模式' : '暗色模式' }}
          </span>
        </button>
      </div>

      <!-- 底部用户区 -->
      <div class="p-2 border-t border-gray-200 dark:border-gray-800 flex-shrink-0">
        <button
          class="flex items-center w-full h-12 px-2 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors overflow-hidden"
          @click="logout"
        >
          <div class="w-12 h-12 flex items-center justify-center flex-shrink-0">
            <div class="w-9 h-9 rounded-full bg-primary-100 dark:bg-primary-900/40 text-primary-700 dark:text-primary-300 flex items-center justify-center text-sm font-semibold">
              {{ (auth.userInfo?.username ?? '?').charAt(0).toUpperCase() }}
            </div>
          </div>
          <div
            class="flex flex-col items-start min-w-0 transition-opacity duration-150"
            :class="hovered ? 'opacity-100' : 'opacity-0'"
          >
            <span class="text-sm font-medium text-gray-800 dark:text-gray-100 whitespace-nowrap">
              {{ auth.userInfo?.username ?? '未登录' }}
            </span>
            <span class="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">点击登出</span>
          </div>
        </button>
      </div>
    </aside>

    <!-- 主区域 -->
    <main class="flex-1 overflow-hidden">
      <RouterView />
    </main>
  </div>
</template>
