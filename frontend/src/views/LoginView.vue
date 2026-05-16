<script setup lang="ts">
/**
 * 登录 / 注册页面
 *
 * 简洁的双 Tab 切换设计，复用同一表单。
 * 登录成功后自动跳转到 query.redirect 或 /。
 */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Eye, EyeOff, Loader2, Lock, User } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import { register } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

// ---------- 状态 ----------
const mode = ref<'login' | 'register'>('login')
const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMsg = ref('')
const showPassword = ref(false)  // 密码可见切换

// ---------- 切换模式 ----------
function switchMode(target: 'login' | 'register') {
  mode.value = target
  errorMsg.value = ''
}

// ---------- 表单提交 ----------
async function handleSubmit() {
  if (!username.value || !password.value) {
    errorMsg.value = '用户名和密码不能为空'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    if (mode.value === 'register') {
      await register(username.value, password.value)
      await auth.login(username.value, password.value)
      toast.success(`欢迎加入，${username.value}`)
    } else {
      await auth.login(username.value, password.value)
      toast.success(`欢迎回来，${username.value}`)
    }
    // 跳转到来源页或首页
    const redirect = (route.query.redirect as string) || '/'
    router.replace(redirect)
  } catch (e: any) {
    errorMsg.value = e?.message || '操作失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 via-white to-indigo-100 dark:from-gray-950 dark:via-gray-900 dark:to-indigo-950 px-4">
    <div class="w-full max-w-md bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-8 space-y-6">
      <!-- 品牌头 -->
      <div class="text-center">
        <h1 class="text-3xl font-bold text-primary-700 dark:text-primary-400">NexusAI</h1>
        <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">企业级智能知识库 + 多 Agent 协作平台</p>
      </div>

      <!-- 模式切换 -->
      <div class="flex border-b border-gray-200 dark:border-gray-800">
        <button
          class="flex-1 py-2 text-sm font-medium transition-colors"
          :class="mode === 'login' ? 'text-primary-600 dark:text-primary-400 border-b-2 border-primary-600 dark:border-primary-400' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
          @click="switchMode('login')"
        >
          登录
        </button>
        <button
          class="flex-1 py-2 text-sm font-medium transition-colors"
          :class="mode === 'register' ? 'text-primary-600 dark:text-primary-400 border-b-2 border-primary-600 dark:border-primary-400' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
          @click="switchMode('register')"
        >
          注册
        </button>
      </div>

      <!-- 表单 -->
      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">用户名</label>
          <div class="relative">
            <User :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              v-model="username"
              type="text"
              autocomplete="username"
              placeholder="3-64 位字母/数字/下划线"
              :disabled="loading"
              class="w-full pl-9 pr-3 py-2 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-60 disabled:bg-gray-50 dark:disabled:bg-gray-900 placeholder:text-gray-400 dark:placeholder:text-gray-500"
            />
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">密码</label>
          <div class="relative">
            <Lock :size="16" class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              autocomplete="current-password"
              placeholder="至少 6 位"
              :disabled="loading"
              class="w-full pl-9 pr-10 py-2 bg-white dark:bg-gray-800 text-gray-800 dark:text-gray-100 border border-gray-300 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent disabled:opacity-60 disabled:bg-gray-50 dark:disabled:bg-gray-900 placeholder:text-gray-400 dark:placeholder:text-gray-500"
            />
            <button
              type="button"
              tabindex="-1"
              class="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 transition-colors"
              :title="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <EyeOff v-if="showPassword" :size="16" />
              <Eye v-else :size="16" />
            </button>
          </div>
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMsg" class="text-sm text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/30 px-3 py-2 rounded-lg">
          {{ errorMsg }}
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 bg-primary-600 text-white rounded-lg font-medium hover:bg-primary-700 transition-colors disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          <Loader2 v-if="loading" :size="16" class="animate-spin" />
          <span>{{ loading ? '处理中...' : mode === 'login' ? '登录' : '注册并登录' }}</span>
        </button>
      </form>

      <p class="text-xs text-center text-gray-400 dark:text-gray-500">
        © 2026 NexusAI · 企业级智能知识库 + 多 Agent 协作平台
      </p>
    </div>
  </div>
</template>
