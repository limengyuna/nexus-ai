<script setup lang="ts">
/**
 * 首页（占位）
 *
 * 阶段一仅做：欢迎信息 + 当前用户信息展示 + 登出按钮。
 * 阶段四将替换为完整的对话/管理界面。
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

// 进入页面时确保用户信息已加载
onMounted(async () => {
  if (!auth.userInfo) {
    try {
      await auth.fetchUserInfo()
    } catch {
      // 拉取失败由 axios 拦截器自动跳转登录页
    }
  }
})

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="min-h-screen bg-gray-50">
    <!-- 顶部导航 -->
    <header class="bg-white shadow-sm">
      <div class="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
        <h1 class="text-xl font-bold text-primary-700">NexusAI</h1>
        <div class="flex items-center gap-4">
          <span class="text-sm text-gray-600">
            {{ auth.userInfo?.username }}
            <span class="ml-2 px-2 py-0.5 text-xs rounded-full bg-primary-100 text-primary-700">
              {{ auth.userInfo?.role }}
            </span>
          </span>
          <button
            class="text-sm text-gray-500 hover:text-red-600 transition-colors"
            @click="handleLogout"
          >
            登出
          </button>
        </div>
      </div>
    </header>

    <!-- 主体 -->
    <main class="max-w-6xl mx-auto px-6 py-12">
      <div class="bg-white rounded-2xl shadow-sm p-8 space-y-6">
        <div>
          <h2 class="text-2xl font-bold text-gray-800">欢迎来到 NexusAI</h2>
          <p class="mt-2 text-gray-500">
            企业级智能知识库 + 多 Agent 协作平台 — 阶段一基座已就绪。
          </p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div class="border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow">
            <div class="text-primary-600 font-semibold mb-2">阶段一 ✓</div>
            <div class="text-sm text-gray-600">FastAPI 基座 + JWT 认证 + 数据库 + Celery</div>
          </div>
          <div class="border border-gray-200 rounded-xl p-5 opacity-60">
            <div class="text-gray-700 font-semibold mb-2">阶段二</div>
            <div class="text-sm text-gray-600">RAG 知识库管道（解析→分块→向量化）</div>
          </div>
          <div class="border border-gray-200 rounded-xl p-5 opacity-60">
            <div class="text-gray-700 font-semibold mb-2">阶段三</div>
            <div class="text-sm text-gray-600">LangGraph 多 Agent + Skills + MCP</div>
          </div>
        </div>

        <div class="text-xs text-gray-400 pt-4 border-t border-gray-100">
          后续阶段将逐步加入对话界面、知识库管理、MCP 配置等功能。
        </div>
      </div>
    </main>
  </div>
</template>
