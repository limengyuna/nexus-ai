<script setup lang="ts">
/**
 * 工作区首页 (Dashboard)
 * 极致冷淡黑白灰风格
 */
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

onMounted(async () => {
  if (!auth.userInfo) {
    try {
      await auth.fetchUserInfo()
    } catch {}
  }
})

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div class="h-full bg-white dark:bg-zinc-950 overflow-y-auto text-zinc-900 dark:text-zinc-100 font-sans">
    
    <!-- 极简 Header，仅通过下边框分隔 -->
    <header class="border-b border-zinc-200 dark:border-zinc-800 bg-white/80 dark:bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-20">
      <div class="px-8 py-5 flex items-center justify-between">
        <h1 class="text-xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-100">Workspace</h1>
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              {{ auth.userInfo?.username }}
            </span>
            <span class="px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider rounded-sm bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400">
              {{ auth.userInfo?.role }}
            </span>
          </div>
        </div>
      </div>
    </header>

    <!-- 主体内容 -->
    <main class="max-w-5xl mx-auto px-8 py-12">
      <div class="space-y-8">
        <!-- 欢迎区 -->
        <div class="space-y-2">
          <h2 class="text-3xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">Welcome to NexusAI</h2>
          <p class="text-sm text-zinc-500 dark:text-zinc-400 max-w-2xl leading-relaxed">
            Enterprise-grade intelligent knowledge base and multi-agent autonomous swarm workspace. Phase 1 foundation is ready.
          </p>
        </div>

        <!-- 状态卡片网格 -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          
          <!-- Phase 1: Completed -->
          <div class="border border-zinc-200 dark:border-zinc-800 rounded-md p-6 bg-zinc-50/50 dark:bg-zinc-900/20 transition-colors">
            <div class="flex items-center justify-between mb-4">
              <div class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Phase 1</div>
              <div class="text-xs font-mono px-2 py-1 bg-zinc-900 text-white dark:bg-white dark:text-zinc-950 rounded-sm">Active</div>
            </div>
            <div class="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
              FastAPI foundation, JWT authentication, vector database integration, and async task processing.
            </div>
          </div>

          <!-- Phase 2: Pending -->
          <div class="border border-zinc-200 dark:border-zinc-800 rounded-md p-6 opacity-60">
            <div class="flex items-center justify-between mb-4">
              <div class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Phase 2</div>
              <div class="text-xs font-mono px-2 py-1 bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400 rounded-sm">Pending</div>
            </div>
            <div class="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
              RAG knowledge pipeline. Document parsing, semantic chunking, and distributed vectorization.
            </div>
          </div>

          <!-- Phase 3: Pending -->
          <div class="border border-zinc-200 dark:border-zinc-800 rounded-md p-6 opacity-60">
            <div class="flex items-center justify-between mb-4">
              <div class="text-sm font-semibold text-zinc-900 dark:text-zinc-100">Phase 3</div>
              <div class="text-xs font-mono px-2 py-1 bg-zinc-100 text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400 rounded-sm">Pending</div>
            </div>
            <div class="text-sm text-zinc-500 dark:text-zinc-400 leading-relaxed">
              LangGraph multi-agent orchestration, custom Skills execution, and MCP protocol integration.
            </div>
          </div>

        </div>

        <div class="pt-8 mt-8 border-t border-zinc-200 dark:border-zinc-800">
          <p class="text-xs text-zinc-400 dark:text-zinc-500">
            Subsequent phases will gradually introduce the conversational interface, knowledge base management, and advanced MCP configurations.
          </p>
        </div>

      </div>
    </main>
  </div>
</template>
