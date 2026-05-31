<script setup lang="ts">
/**
 * 登录 / 注册页面
 *
 * 极简双栏设计，严格的黑白灰冷淡美学。
 * 登录成功后自动跳转到 query.redirect 或 /。
 */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Loader2 } from 'lucide-vue-next'
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

// ---------- 切换模式 ----------
function switchMode(target: 'login' | 'register') {
  mode.value = target
  errorMsg.value = ''
}

// ---------- 表单提交 ----------
async function handleSubmit() {
  if (!username.value || !password.value) {
    errorMsg.value = 'Username and password cannot be empty.'
    return
  }
  loading.value = true
  errorMsg.value = ''
  try {
    if (mode.value === 'register') {
      await register(username.value, password.value)
      await auth.login(username.value, password.value)
      toast.success(`Welcome, ${username.value}.`)
    } else {
      await auth.login(username.value, password.value)
      toast.success(`Welcome back, ${username.value}.`)
    }
    const redirect = (route.query.redirect as string) || '/'
    router.replace(redirect)
  } catch (e: any) {
    errorMsg.value = e?.message || 'Operation failed. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="relative min-h-screen flex bg-white dark:bg-zinc-950 overflow-hidden font-sans">
    
    <!-- 左半边：极简宣言区（仅大屏展示） -->
    <!-- 使用完全纯净的锌灰底色，与右侧的纯白形成强烈对比 -->
    <div class="hidden lg:flex lg:w-1/2 relative z-10 flex-col justify-between p-12 xl:p-20 bg-zinc-950 dark:bg-zinc-900 overflow-hidden">
      
      <!-- 质感背景层 (已调亮以显露结构细节) -->
      <div class="absolute inset-0 z-0 pointer-events-none select-none opacity-70">
        <img 
          src="/hero_bg.png" 
          alt="NexusAI Texture" 
          class="w-full h-full object-cover object-center scale-105"
        />
        <!-- 轻度遮罩处理，确保白色文字区域依然清晰，释放画面上方的细节 -->
        <div class="absolute inset-0 bg-gradient-to-t from-zinc-950 via-zinc-950/40 to-transparent"></div>
        <div class="absolute inset-0 bg-gradient-to-r from-zinc-950/70 via-transparent to-transparent"></div>
      </div>

      <!-- 品牌信息 -->
      <div class="flex items-center gap-3 relative z-10 text-white">
        <!-- 极致几何标志 -->
        <div class="w-8 h-8 rounded-sm bg-white text-zinc-950 flex items-center justify-center flex-shrink-0">
          <svg viewBox="0 0 24 24" fill="none" class="w-4 h-4 flex-shrink-0" xmlns="http://www.w3.org/2000/svg">
            <path d="M6 17C6 11 8 7 11 7s5 3 5 8" stroke="currentColor" stroke-width="3" stroke-linecap="square" />
            <path d="M18 7C18 13 16 17 13 17s-5-3-5-8" stroke="currentColor" stroke-width="3" stroke-linecap="square" />
          </svg>
        </div>
        <span class="text-xl font-bold tracking-tight">NexusAI</span>
      </div>

      <!-- 纯排版视觉宣言 -->
      <div class="max-w-md my-auto space-y-6 relative z-10">
        <h2 class="text-4xl md:text-5xl font-semibold tracking-tighter text-white leading-[1.1]">
          Intelligence without the noise.
        </h2>
        <p class="text-base text-zinc-400 font-medium leading-relaxed">
          The autonomous workspace for reasoning agents and structured knowledge. Connect your enterprise data, deploy agentic workflows, and scale your operations quietly.
        </p>
      </div>

      <!-- 页脚版权 -->
      <div class="text-xs text-zinc-600 font-medium tracking-wide relative z-10">
        © 2026 NexusAI.
      </div>
    </div>

    <!-- 右半边：空气感极简表单区 -->
    <div class="flex-1 relative z-10 flex items-center justify-center p-8 lg:p-16">
      <div class="w-full max-w-sm space-y-10">
        
        <!-- 移动端专用头部 -->
        <div class="text-center lg:hidden space-y-4">
          <div class="inline-flex w-10 h-10 rounded-sm bg-zinc-950 dark:bg-white text-white dark:text-zinc-950 items-center justify-center flex-shrink-0">
            <svg viewBox="0 0 24 24" fill="none" class="w-5 h-5 flex-shrink-0" xmlns="http://www.w3.org/2000/svg">
              <path d="M6 17C6 11 8 7 11 7s5 3 5 8" stroke="currentColor" stroke-width="3" stroke-linecap="square" />
              <path d="M18 7C18 13 16 17 13 17s-5-3-5-8" stroke="currentColor" stroke-width="3" stroke-linecap="square" />
            </svg>
          </div>
          <h1 class="text-2xl font-bold text-zinc-900 dark:text-zinc-100 tracking-tight">NexusAI</h1>
        </div>

        <!-- 表单头部 -->
        <div class="hidden lg:block space-y-1">
          <h2 class="text-2xl font-semibold text-zinc-950 dark:text-zinc-50 tracking-tight">
            {{ mode === 'login' ? 'Log in to your account' : 'Create an account' }}
          </h2>
          <p class="text-sm text-zinc-500 dark:text-zinc-400">
            {{ mode === 'login' ? 'Enter your credentials to access your workspace.' : 'Set up your credentials to begin.' }}
          </p>
        </div>

        <!-- 表单区域 -->
        <form class="space-y-6" @submit.prevent="handleSubmit">
          
          <div class="space-y-4">
            <!-- 用户名输入 -->
            <div class="space-y-2">
              <label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Username</label>
              <input
                v-model="username"
                type="text"
                autocomplete="username"
                :disabled="loading"
                class="w-full px-3 py-2.5 bg-transparent text-zinc-900 dark:text-zinc-100 border border-zinc-300 dark:border-zinc-700 rounded-md focus:outline-none focus:border-zinc-950 dark:focus:border-zinc-300 transition-colors duration-200 disabled:opacity-50"
              />
            </div>

            <!-- 密码输入 -->
            <div class="space-y-2">
              <div class="flex items-center justify-between">
                <label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Password</label>
              </div>
              <input
                v-model="password"
                type="password"
                autocomplete="current-password"
                :disabled="loading"
                class="w-full px-3 py-2.5 bg-transparent text-zinc-900 dark:text-zinc-100 border border-zinc-300 dark:border-zinc-700 rounded-md focus:outline-none focus:border-zinc-950 dark:focus:border-zinc-300 transition-colors duration-200 disabled:opacity-50"
              />
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="errorMsg" class="text-sm text-red-600 dark:text-red-400">
            {{ errorMsg }}
          </div>

          <!-- 提交按钮 -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 bg-zinc-950 hover:bg-zinc-900 dark:bg-white dark:hover:bg-zinc-100 text-white dark:text-zinc-950 rounded-md font-medium transition-colors duration-200 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2"
          >
            <Loader2 v-if="loading" :size="16" class="animate-spin" />
            <span>{{ mode === 'login' ? 'Continue' : 'Sign up' }}</span>
          </button>
        </form>

        <!-- 极简模式切换 -->
        <div class="text-center">
          <button
            type="button"
            class="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100 transition-colors"
            @click="switchMode(mode === 'login' ? 'register' : 'login')"
          >
            {{ mode === 'login' ? 'Need an account? Sign up' : 'Already have an account? Log in' }}
          </button>
        </div>

      </div>
    </div>
  </div>
</template>
