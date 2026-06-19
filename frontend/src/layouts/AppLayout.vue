<script setup lang="ts">
/**
 * 应用主布局
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
  logoClickTimer = setTimeout(() => { logoClickCount = 0 }, 2000)
}

onMounted(async () => {
  if (!auth.userInfo) {
    try {
      await auth.fetchUserInfo()
    } catch {}
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

const navItems: NavItem[] = [
  { to: '/chat', label: 'Chat', icon: markRaw(MessageSquare) },
  { to: '/knowledge', label: 'Knowledge Base', icon: markRaw(Library) },
  { to: '/skills', label: 'Skills', icon: markRaw(Sparkles) },
  { to: '/mcp', label: 'MCP Config', icon: markRaw(Plug) },
  { to: '/memory', label: 'Memory', icon: markRaw(Brain) },
]
</script>

<template>
  <div class="flex h-screen bg-white dark:bg-zinc-950 relative font-sans text-zinc-900 dark:text-zinc-100">
    <div class="hidden md:block w-16 flex-shrink-0"></div>

    <!-- 侧栏：桌面端显示，移动端隐藏 (固定 w-16) -->
    <aside
      class="hidden md:flex absolute top-0 left-0 h-screen w-16 bg-zinc-50/80 dark:bg-zinc-900/60 backdrop-blur-xl border-r border-zinc-200/80 dark:border-zinc-800/60 flex-col z-40 transition-colors"
    >
      <!-- 品牌区 -->
      <div class="h-16 flex items-center justify-center border-b border-zinc-200 dark:border-zinc-800 flex-shrink-0">
        <div
          class="w-10 h-10 rounded-sm bg-zinc-950 text-white dark:bg-white dark:text-zinc-950 flex items-center justify-center flex-shrink-0 cursor-pointer select-none transition-transform active:scale-95 hover:scale-105"
          @click="handleLogoClick"
        >
          <svg viewBox="0 0 24 24" fill="none" class="w-5 h-5 flex-shrink-0" xmlns="http://www.w3.org/2000/svg">
            <path d="M6 17C6 11 8 7 11 7s5 3 5 8" stroke="currentColor" stroke-width="3" stroke-linecap="square" />
            <path d="M18 7C18 13 16 17 13 17s-5-3-5-8" stroke="currentColor" stroke-width="3" stroke-linecap="square" />
          </svg>
        </div>
      </div>

      <!-- 图标导航 -->
      <nav class="flex-1 py-4 px-2.5 overflow-y-auto">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="relative flex items-center h-11 px-1 mb-1.5 rounded-xl transition-all duration-200 overflow-hidden group"
          :class="route.path.startsWith(item.to)
            ? 'bg-white dark:bg-zinc-800 shadow-sm border border-zinc-200/50 dark:border-zinc-700/50 text-zinc-900 dark:text-white font-semibold'
            : 'text-zinc-500 dark:text-zinc-400 hover:bg-zinc-200/60 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-100 border border-transparent'"
        >
          <!-- 图标容器 -->
          <div class="w-10 h-10 flex items-center justify-center flex-shrink-0">
            <component 
              :is="item.icon" 
              :size="18" 
              :stroke-width="route.path.startsWith(item.to) ? 2.5 : 2" 
              class="transition-transform duration-200 group-hover:scale-110"
            />
          </div>
          <!-- Tooltip 标签 -->
          <span class="absolute left-full ml-1 px-2.5 py-1.5 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-semibold rounded-md opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 pointer-events-none whitespace-nowrap shadow-md z-50">
            {{ item.label }}
          </span>
        </RouterLink>
      </nav>

      <!-- 主题切换按钮 -->
      <div class="px-2.5 pb-2 flex-shrink-0">
        <button
          class="flex items-center w-full h-11 px-1 rounded-xl text-zinc-500 dark:text-zinc-400 hover:bg-zinc-200/60 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors duration-150 overflow-hidden group"
          :title="theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'"
          @click="toggleTheme"
        >
          <div class="w-10 h-10 flex items-center justify-center flex-shrink-0">
            <Sun v-if="theme === 'dark'" :size="18" :stroke-width="2" class="group-hover:text-zinc-100 transition-colors" />
            <Moon v-else :size="18" :stroke-width="2" class="group-hover:text-zinc-900 transition-colors" />
          </div>
          <!-- Tooltip -->
          <span class="absolute left-full ml-1 px-2.5 py-1.5 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-semibold rounded-md opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 pointer-events-none whitespace-nowrap shadow-md z-50">
            {{ theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode' }}
          </span>
        </button>
      </div>

      <!-- 底部用户区 -->
      <div class="p-2.5 border-t border-zinc-200 dark:border-zinc-800 flex-shrink-0">
        <button
          class="flex items-center w-full h-12 px-1 rounded-xl hover:bg-zinc-200/60 dark:hover:bg-zinc-800/50 transition-colors duration-150 overflow-hidden group"
          @click="logout"
        >
          <div class="w-10 h-10 flex items-center justify-center flex-shrink-0">
            <div class="w-8 h-8 rounded-lg bg-zinc-200 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300 flex items-center justify-center text-xs font-bold group-hover:bg-zinc-300 dark:group-hover:bg-zinc-700 transition-colors">
              {{ (auth.userInfo?.username ?? '?').charAt(0).toUpperCase() }}
            </div>
          </div>
          <!-- Tooltip -->
          <span class="absolute left-full ml-1 px-2.5 py-1.5 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-semibold rounded-md opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200 pointer-events-none whitespace-nowrap shadow-md z-50">
            Sign out ({{ auth.userInfo?.username ?? 'Guest' }})
          </span>
        </button>
      </div>
    </aside>

    <!-- 移动端底部导航栏 -->
    <nav class="md:hidden fixed bottom-0 left-0 right-0 h-14 bg-zinc-50/90 dark:bg-zinc-950/90 backdrop-blur-md border-t border-zinc-200/50 dark:border-zinc-800/50 flex items-center justify-around z-40 px-2 shadow-lg">
      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="flex flex-col items-center justify-center flex-1 h-full text-zinc-400 dark:text-zinc-500 select-none active:scale-95 transition-transform"
        :class="route.path.startsWith(item.to) ? 'text-zinc-950 dark:text-zinc-50' : 'hover:text-zinc-700 dark:hover:text-zinc-300'"
      >
        <component
          :is="item.icon"
          :size="18"
          :stroke-width="route.path.startsWith(item.to) ? 2.5 : 2"
        />
        <span class="text-[9px] font-bold mt-1 tracking-tight">
          {{ item.label }}
        </span>
      </RouterLink>
    </nav>

    <!-- 主区域：移动端预留底部导航栏高度 -->
    <main class="flex-1 overflow-hidden relative z-10 bg-white dark:bg-zinc-950 pb-14 md:pb-0">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>

</style>
