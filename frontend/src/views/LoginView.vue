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

const usernameFocused = ref(false) // 用户名聚焦状态
const passwordFocused = ref(false) // 密码聚焦状态

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
  <div class="relative min-h-screen flex bg-[#fcfaf7] dark:bg-[#07080d] overflow-hidden">
    <!-- 太极砂褐微细科技网格 -->
    <div class="absolute inset-0 z-0 bg-[radial-gradient(rgba(200,179,160,0.12)_1px,transparent_1px)] dark:bg-[radial-gradient(rgba(255,255,255,0.03)_1px,transparent_1px)] [background-size:24px_24px] pointer-events-none opacity-85"></div>

    <!-- 动态高空流光极光发光球 -->
    <div class="absolute inset-0 z-0 overflow-hidden pointer-events-none">
      <div class="absolute -top-[20%] -left-[10%] w-[70vw] h-[70vw] rounded-full bg-gradient-to-br from-yellow-100/10 to-amber-100/10 blur-[130px] dark:from-yellow-950/5 dark:to-amber-950/5 animate-aurora-1"></div>
      <div class="absolute -bottom-[20%] -right-[10%] w-[60vw] h-[60vw] rounded-full bg-gradient-to-br from-orange-100/10 to-amber-100/10 blur-[120px] dark:from-amber-950/5 dark:to-gray-950/5 animate-aurora-2"></div>
      <div class="absolute top-[30%] left-[30%] w-[50vw] h-[50vw] rounded-full bg-gradient-to-br from-amber-50/10 to-yellow-50/10 blur-[100px] dark:from-yellow-950/5 dark:to-zinc-950/5 animate-aurora-3"></div>
    </div>

    <!-- 左半边：艺术与平台特性看板区（仅大屏展示） -->
    <div class="hidden lg:flex lg:w-[55%] xl:w-[58%] relative z-10 flex-col justify-between p-16 border-r border-gray-100/50 dark:border-gray-800/10 overflow-hidden">
      <!-- 官网级 3D 磨砂几何流光主插图（通过 CSS mask 进行底色渐变融合，极具空间纵深） -->
      <div class="absolute inset-0 z-0 pointer-events-none select-none">
        <img 
          src="/hero.png" 
          alt="NexusAI Hero" 
          class="w-full h-full object-cover object-center opacity-70 dark:opacity-35 transition-opacity duration-300"
        />
        <!-- 渐变掩膜：实现图片与燕麦白宣纸纸面的无缝边缘融合 -->
        <div class="absolute inset-0 bg-gradient-to-r from-transparent via-[#fcfaf7]/40 to-[#fcfaf7] dark:via-[#07080d]/40 dark:to-[#07080d]"></div>
        <div class="absolute inset-0 bg-gradient-to-t from-[#fcfaf7] via-transparent to-transparent dark:from-[#07080d]"></div>
      </div>

      <!-- 品牌信息（浮于大图上，带有微磨砂感） -->
      <div class="flex items-center gap-3 relative z-10">
        <!-- 方案一：高奢太极砂褐三维无限纽带标 -->
        <div class="w-9 h-9 rounded-xl bg-gradient-to-br from-[#faf9f6]/95 to-[#eae4dc]/95 dark:from-gray-800/90 dark:to-gray-900/90 border border-white/80 dark:border-white/5 shadow-[inset_0_1.5px_2.5px_rgba(255,255,255,0.7),0_4px_12px_rgba(200,179,160,0.08)] dark:shadow-[inset_0_1px_1px_rgba(255,255,255,0.1),0_4px_12px_rgba(0,0,0,0.3)] flex items-center justify-center transition-all duration-300 hover:scale-[1.05] hover:rotate-6 flex-shrink-0">
          <svg viewBox="0 0 24 24" fill="none" class="w-5 h-5 flex-shrink-0" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="logo-sand-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#e3d5ca" />
                <stop offset="50%" stop-color="#c8b3a0" />
                <stop offset="100%" stop-color="#9c8470" />
              </linearGradient>
              <linearGradient id="logo-charcoal-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#8c92ac" />
                <stop offset="100%" stop-color="#4b526d" />
              </linearGradient>
            </defs>
            <path d="M6 17C6 11 8 7 11 7s5 3 5 8-2 6-5 6" stroke="url(#logo-sand-grad)" stroke-width="2.5" stroke-linecap="round" />
            <path d="M18 7C18 13 16 17 13 17s-5-3-5-8 2-6 5-6" stroke="url(#logo-charcoal-grad)" stroke-width="2.5" stroke-linecap="round" style="mix-blend-mode: multiply; opacity: 0.95;" />
          </svg>
        </div>
        <span class="text-lg font-bold font-outfit text-gray-800 dark:text-gray-200 tracking-tight">NexusAI</span>
      </div>

      <!-- Slogan 与 特性卡片展示（浮于大图上，带有微磨砂感） -->
      <div class="max-w-xl my-auto space-y-12 pr-6 relative z-10">
        <div class="space-y-4">
          <h2 class="text-4xl font-extrabold font-outfit tracking-tight text-gray-800 dark:text-gray-100 leading-tight">
            下一代智能知识库<br />
            <span class="text-[#9c8470] dark:text-[#c8b3a0]">与多智能体协作平台</span>
          </h2>
          <p class="text-xs text-gray-500 dark:text-gray-400 font-medium leading-relaxed max-w-md">
            The next generation intelligent knowledge base and multi-agent autonomous swarm workspace. Connect your data, deploy reasoning agents, and automate workflows in seconds.
          </p>
        </div>

        <!-- 3个超轻毛玻璃特性卡片 -->
        <div class="grid grid-cols-3 gap-4">
          <!-- 特性 1 -->
          <div class="p-4 bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-2xl border border-white/30 dark:border-white/5 shadow-[0_8px_32px_0_rgba(200,179,160,0.03)] transition-all hover:scale-[1.02] duration-300">
            <div class="w-8 h-8 rounded-lg bg-[#faf9f5]/90 dark:bg-gray-800/50 border border-gray-200/30 dark:border-gray-800/30 flex items-center justify-center mb-3">
              <!-- 精选阿里的雷达星芒AI检索 SVG -->
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="w-3.5 h-3.5 text-gray-700 dark:text-gray-300">
                <circle cx="11" cy="11" r="6" />
                <path d="M21 21l-4.3-4.3" />
                <path d="M15 7a2 2 0 002-2 2 2 0 002 2 2 2 0 00-2 2 2 2 0 00-2-2z" />
                <path d="M9 14a1.5 1.5 0 001.5-1.5 1.5 1.5 0 001.5 1.5 1.5 1.5 0 00-1.5 1.5 1.5 1.5 0 00-1.5-1.5z" />
              </svg>
            </div>
            <h3 class="text-xs font-bold text-gray-800 dark:text-gray-200 mb-1">毫秒级检索</h3>
            <p class="text-[9px] text-gray-400 dark:text-gray-500 leading-relaxed font-medium">企业级数据精准切片与极速语义检索。</p>
          </div>
          <!-- 特性 2 -->
          <div class="p-4 bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-2xl border border-white/30 dark:border-white/5 shadow-[0_8px_32px_0_rgba(200,179,160,0.03)] transition-all hover:scale-[1.02] duration-300">
            <div class="w-8 h-8 rounded-lg bg-[#faf9f5]/90 dark:bg-gray-800/50 border border-gray-200/30 dark:border-gray-800/30 flex items-center justify-center mb-3">
              <!-- 精选阿里的多智能体协同链接网络 SVG -->
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="w-3.5 h-3.5 text-gray-700 dark:text-gray-300">
                <circle cx="12" cy="5" r="2.5" />
                <circle cx="5" cy="17" r="2.5" />
                <circle cx="19" cy="17" r="2.5" />
                <path d="M10.5 7.5l-4 6.5" />
                <path d="M13.5 7.5l4 6.5" />
                <path d="M7.5 17h9" />
                <circle cx="12" cy="12" r="1.5" />
              </svg>
            </div>
            <h3 class="text-xs font-bold text-gray-800 dark:text-gray-200 mb-1">智能体协同</h3>
            <p class="text-[9px] text-gray-400 dark:text-gray-500 leading-relaxed font-medium">多 Agent 跨渠道协作，构建自主流。</p>
          </div>
          <!-- 特性 3 -->
          <div class="p-4 bg-white/50 dark:bg-gray-900/40 backdrop-blur-md rounded-2xl border border-white/30 dark:border-white/5 shadow-[0_8px_32px_0_rgba(200,179,160,0.03)] transition-all hover:scale-[1.02] duration-300">
            <div class="w-8 h-8 rounded-lg bg-[#faf9f5]/90 dark:bg-gray-800/50 border border-gray-200/30 dark:border-gray-800/30 flex items-center justify-center mb-3">
              <!-- 精选阿里的智脑神经芯片持久化记忆 SVG -->
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="w-3.5 h-3.5 text-gray-700 dark:text-gray-300">
                <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96-.44 2.5 2.5 0 0 1 0-3.12 3 3 0 0 1 0-4.88 2.5 2.5 0 0 1 0-3.12A2.5 2.5 0 0 1 9.5 2z" />
                <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96-.44 2.5 2.5 0 0 0 0-3.12 3 3 0 0 0 0-4.88 2.5 2.5 0 0 0 0-3.12A2.5 2.5 0 0 0 14.5 2z" />
                <circle cx="12" cy="12" r="1.5" />
              </svg>
            </div>
            <h3 class="text-xs font-bold text-gray-800 dark:text-gray-200 mb-1">持久化记忆</h3>
            <p class="text-[9px] text-gray-400 dark:text-gray-500 leading-relaxed font-medium">智能追踪核心上下文，长效遗忘控制。</p>
          </div>
        </div>
      </div>

      <!-- 页脚版权 -->
      <div class="text-[10px] text-gray-400 dark:text-gray-500 font-medium tracking-wide relative z-10">
        © 2026 NexusAI · Enterprise-grade Knowledge Workspace.
      </div>
    </div>

    <!-- 右半边：空气感极简表单区 -->
    <div class="flex-1 relative z-10 flex items-center justify-center p-8 lg:p-16">
      <div class="w-full max-w-sm space-y-8">
        <!-- 移动端专用头部（仅在小屏下展示） -->
        <div class="text-center lg:hidden space-y-3">
          <div class="inline-flex w-11 h-11 rounded-xl bg-gradient-to-br from-[#faf9f6]/95 to-[#eae4dc]/95 dark:from-gray-800/90 dark:to-gray-900/90 border border-white/80 dark:border-white/5 shadow-[inset_0_1.5px_2.5px_rgba(255,255,255,0.7),0_4px_12px_rgba(200,179,160,0.08)] dark:shadow-[inset_0_1px_1px_rgba(255,255,255,0.1),0_4px_12px_rgba(0,0,0,0.3)] items-center justify-center transition-all duration-300 hover:scale-[1.05] hover:rotate-6 flex-shrink-0">
            <svg viewBox="0 0 24 24" fill="none" class="w-6 h-6 flex-shrink-0" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="logo-sand-grad-mb" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#e3d5ca" />
                  <stop offset="50%" stop-color="#c8b3a0" />
                  <stop offset="100%" stop-color="#9c8470" />
                </linearGradient>
                <linearGradient id="logo-charcoal-grad-mb" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#8c92ac" />
                  <stop offset="100%" stop-color="#4b526d" />
                </linearGradient>
              </defs>
              <path d="M6 17C6 11 8 7 11 7s5 3 5 8-2 6-5 6" stroke="url(#logo-sand-grad-mb)" stroke-width="2.5" stroke-linecap="round" />
              <path d="M18 7C18 13 16 17 13 17s-5-3-5-8 2-6 5-6" stroke="url(#logo-charcoal-grad-mb)" stroke-width="2.5" stroke-linecap="round" style="mix-blend-mode: multiply; opacity: 0.95;" />
            </svg>
          </div>
          <h1 class="text-3xl font-extrabold font-outfit text-gray-800 dark:text-gray-100">NexusAI</h1>
          <p class="text-xs text-gray-500 dark:text-gray-400 tracking-wider">企业级智能知识库与多 Agent 协作</p>
        </div>

        <!-- 亮色端专属表单标题 -->
        <div class="hidden lg:block space-y-2">
          <h2 class="text-2xl font-bold text-gray-800 dark:text-gray-100 tracking-tight">
            {{ mode === 'login' ? '欢迎回来' : '开启智能之旅' }}
          </h2>
          <p class="text-xs text-gray-400 dark:text-gray-500 font-medium">请输入您的账户凭证以登录您的工作空间</p>
        </div>

        <!-- 高阶弹性滑动胶囊 Tab 切换 -->
        <div class="relative flex p-1 bg-gray-100/80 dark:bg-gray-800/40 rounded-xl glass-border">
          <div 
            class="absolute top-1 bottom-1 left-1 rounded-lg bg-white dark:bg-gray-900 shadow-sm transition-all duration-300 ease-out"
            :style="{ 
              width: 'calc(50% - 4px)',
              transform: mode === 'login' ? 'translateX(0)' : 'translateX(100%)' 
            }"
          ></div>
          
          <button
            type="button"
            class="relative z-10 flex-1 py-1.5 text-xs font-semibold rounded-lg transition-colors duration-200"
            :class="mode === 'login' ? 'text-gray-800 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            @click="switchMode('login')"
          >
            登录
          </button>
          <button
            type="button"
            class="relative z-10 flex-1 py-1.5 text-xs font-semibold rounded-lg transition-colors duration-200"
            :class="mode === 'register' ? 'text-gray-800 dark:text-white' : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'"
            @click="switchMode('register')"
          >
            注册
          </button>
        </div>

        <!-- 表单区域 -->
        <form class="space-y-4" @submit.prevent="handleSubmit">
          <!-- 用户名 -->
          <div class="space-y-1.5">
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 ml-1">用户名</label>
            <div class="relative">
              <User 
                :size="15" 
                class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors duration-200"
                :class="usernameFocused ? 'text-gray-700 dark:text-gray-300' : ''"
              />
              <input
                v-model="username"
                type="text"
                autocomplete="username"
                placeholder="3-64 位字母/数字/下划线"
                :disabled="loading"
                @focus="usernameFocused = true"
                @blur="usernameFocused = false"
                class="w-full pl-9 pr-3 py-2.5 bg-white/60 dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-xl focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 transition-all duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500 disabled:opacity-60"
              />
            </div>
          </div>

          <!-- 密码 -->
          <div class="space-y-1.5">
            <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 ml-1">密码</label>
            <div class="relative">
              <Lock 
                :size="15" 
                class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 transition-colors duration-200"
                :class="passwordFocused ? 'text-gray-700 dark:text-gray-300' : ''"
              />
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="至少 6 位"
                :disabled="loading"
                @focus="passwordFocused = true"
                @blur="passwordFocused = false"
                class="w-full pl-9 pr-10 py-2.5 bg-white/60 dark:bg-gray-900/50 text-gray-800 dark:text-gray-100 border border-gray-200 dark:border-gray-800 rounded-xl focus:outline-none focus:ring-4 focus:ring-primary-500/10 focus:border-primary-500 transition-all duration-200 placeholder:text-gray-400 dark:placeholder:text-gray-500 disabled:opacity-60"
              />
              <button
                type="button"
                tabindex="-1"
                class="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                :title="showPassword ? '隐藏密码' : '显示密码'"
                @click="showPassword = !showPassword"
              >
                <EyeOff v-if="showPassword" :size="15" />
                <Eye v-else :size="15" />
              </button>
            </div>
          </div>

          <!-- 错误提示 -->
          <transition
            enter-active-class="transition-all duration-200 ease-out"
            enter-from-class="opacity-0 -translate-y-1"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition-all duration-150 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 -translate-y-1"
          >
            <div v-if="errorMsg" class="text-xs text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-950/30 px-3.5 py-2.5 rounded-xl border border-red-200/50 dark:border-red-900/30">
              {{ errorMsg }}
            </div>
          </transition>

          <!-- 极光扫光渐变按钮 -->
          <button
            type="submit"
            :disabled="loading"
            class="w-full py-2.5 bg-gradient-to-r from-gray-800 to-gray-700 hover:from-gray-900 hover:to-gray-800 text-white rounded-xl font-semibold transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2 btn-shine-effect shadow-md hover:shadow-gray-800/10 active:scale-[0.98]"
          >
            <Loader2 v-if="loading" :size="15" class="animate-spin" />
            <span>{{ loading ? '处理中...' : mode === 'login' ? '登录' : '注册并登录' }}</span>
          </button>
        </form>

        <!-- 移动端底部版权 -->
        <p class="lg:hidden text-[9px] text-center text-gray-400 dark:text-gray-500 font-medium tracking-wide">
          © 2026 NexusAI · 企业级智能协作平台
        </p>
      </div>
    </div>
  </div>
</template>
