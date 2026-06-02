<script setup lang="ts">
/**
 * 404 页面
 */
import { useRouter } from 'vue-router'
import { ArrowLeft, Home } from 'lucide-vue-next'

import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

function goBack() {
  // 浏览器历史无记录时回首页
  if (window.history.length > 1) {
    router.back()
  } else {
    goHome()
  }
}

function goHome() {
  // 已登录回到 /chat，未登录回到 /login
  router.replace(auth.isAuthenticated ? '/chat' : '/login')
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-white to-indigo-100 dark:from-gray-950 dark:via-gray-900 dark:to-indigo-950 px-4">
    <div class="text-center max-w-md">

      <h1 class="text-[8rem] leading-none font-extrabold bg-gradient-to-br from-primary-500 to-indigo-600 dark:from-primary-400 dark:to-indigo-400 bg-clip-text text-transparent select-none">
        404
      </h1>

      <h2 class="text-xl font-semibold text-gray-800 dark:text-gray-100 mt-2">页面找不到了</h2>
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-2 leading-relaxed">
        你访问的页面可能已被移除、改名，或暂时不可用。
      </p>

      <div class="flex justify-center gap-3 mt-8">
        <button
          class="flex items-center gap-1.5 px-4 py-2 text-sm text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-700 rounded-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          @click="goBack"
        >
          <ArrowLeft :size="16" />
          <span>返回上一页</span>
        </button>
        <button
          class="flex items-center gap-1.5 px-4 py-2 text-sm text-white dark:text-zinc-900 bg-zinc-900 dark:bg-zinc-100 rounded-sm hover:bg-zinc-800 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 dark:text-zinc-900 transition-colors"
          @click="goHome"
        >
          <Home :size="16" />
          <span>回到首页</span>
        </button>
      </div>
    </div>
  </div>
</template>
