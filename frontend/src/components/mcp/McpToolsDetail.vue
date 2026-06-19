<script setup lang="ts">
import { ref, watch } from 'vue'
import { Edit3, Loader2, Sparkles, X, Check, RefreshCw } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import * as mcpApi from '@/api/mcp'
import type { MCPServerConfig, MCPToolInfo } from '@/api/mcp'

const props = defineProps<{
  server?: MCPServerConfig
  activeServerId: number | null
  activeView: 'list' | 'details'
  activeTools: MCPToolInfo[]
  loadingTools: boolean
  toolError: string
  refreshing: boolean
}>()

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'refresh-cache'): void
  (e: 'desc-updated', updatedDesc: string): void
}>()

// 编辑描述相关的状态
const editingDesc = ref(false)
const editDescValue = ref('')
const savingDesc = ref(false)
const generatingEditDesc = ref(false)

// 监听 server 变化，自动关闭编辑状态并重置文本
watch(() => props.server?.id, () => {
  editingDesc.value = false
  editDescValue.value = props.server?.description || ''
})

async function handleRegenerateEditDesc() {
  if (!props.server) return
  generatingEditDesc.value = true
  try {
    const res = await mcpApi.generateMcpDescription({
      server_name: props.server.name || '外部 MCP',
      tools: props.activeTools,
    })
    editDescValue.value = res.description
    toast.success('AI 描述总结成功，请确认后保存')
  } catch (e: any) {
    toast.error(`AI 总结描述失败: ${e?.message ?? '未知错误'}`)
  } finally {
    generatingEditDesc.value = false
  }
}

async function handleSaveDesc() {
  if (!props.server) return
  savingDesc.value = true
  try {
    const updated = await mcpApi.updateMcpServer(props.server.id, {
      description: editDescValue.value,
    })
    emit('desc-updated', updated.description || '')
    editingDesc.value = false
    toast.success('整体描述更新成功')
  } catch (e: any) {
    toast.error(`更新描述失败: ${e?.message ?? '未知错误'}`)
  } finally {
    savingDesc.value = false
  }
}

function startEditing() {
  editingDesc.value = true
  editDescValue.value = props.server?.description || ''
}
</script>

<template>
  <div 
    class="flex-grow flex flex-col bg-white dark:bg-gray-950"
    :class="{'hidden md:flex': activeServerId === null || activeView === 'list'}"
  >
    <div v-if="!activeServerId" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
      请选择或新建一个 MCP Server
    </div>

    <template v-else>
      <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-800 space-y-3">
        <!-- 移动端返回按钮 -->
        <button
          @click="$emit('back')"
          class="md:hidden flex items-center gap-1.5 text-xs text-zinc-700 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-800 rounded px-2.5 py-1.5 self-start active:scale-95 transition-transform bg-zinc-50 dark:bg-zinc-900"
        >
          ← 返回服务器列表
        </button>
        <!-- 第一行：服务名 & 强制刷新 -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-xl font-bold text-gray-900 dark:text-gray-100">
              {{ server?.name }}
            </h2>
            <span class="px-2 py-0.5 text-xs bg-zinc-100 text-zinc-700 border border-zinc-200 rounded-full dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700 font-medium">
              {{ activeTools.length }} 个工具已预缓存
            </span>
          </div>
          <button 
            class="text-xs text-zinc-900 dark:text-zinc-100 hover:text-primary-300 flex items-center justify-center gap-1.5 py-1.5 px-2.5 border border-zinc-200 dark:border-zinc-800 rounded-sm hover:bg-zinc-100 dark:hover:bg-primary-900/10 disabled:opacity-50 self-start sm:self-center"
            :disabled="refreshing"
            @click="$emit('refresh-cache')"
          >
            <RefreshCw :size="12" :stroke-width="2.5" :class="refreshing ? 'animate-spin' : ''" />
            <span>{{ refreshing ? '重新连接刷新中...' : '强制连接外部刷新工具' }}</span>
          </button>
        </div>

        <!-- 第二行：整体描述展示与编辑 -->
        <div class="bg-zinc-50 dark:bg-zinc-900/40 rounded-xl p-5 shadow-sm ring-1 ring-black/[0.03] dark:ring-white/[0.05]">
          <!-- 默认展示状态 -->
          <div v-if="!editingDesc" class="flex items-start justify-between gap-4 group">
            <div class="flex-1 min-w-0">
              <span class="block text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-1">
                Supervisor 调度大纲描述 (Description)
              </span>
              <p 
                v-if="server?.description" 
                class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed font-normal whitespace-pre-wrap"
              >
                {{ server.description }}
              </p>
              <p v-else class="text-sm text-gray-400 dark:text-gray-500 italic">
                (暂无大纲描述。推荐添加描述，以便 Supervisor 准确地拆解子步骤并调度该服务)
              </p>
            </div>
            <button 
              class="flex-shrink-0 flex items-center gap-1 text-xs text-zinc-900 dark:text-zinc-100 font-medium bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 rounded-sm px-2.5 py-1"
              @click="startEditing"
            >
              <Edit3 :size="12" />
              <span>修改描述</span>
            </button>
          </div>

          <!-- 编辑描述状态 -->
          <div v-else class="space-y-2.5">
            <div class="flex items-center justify-between">
              <span class="block text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">
                修改大纲描述
              </span>
              
              <button 
                class="text-xs text-zinc-900 dark:text-zinc-100 flex items-center gap-1 disabled:opacity-50"
                :disabled="generatingEditDesc"
                @click="handleRegenerateEditDesc"
              >
                <Loader2 v-if="generatingEditDesc" :size="12" class="animate-spin" />
                <Sparkles v-else :size="12" />
                <span>🪄 用 AI 根据子工具重新总结</span>
              </button>
            </div>

            <textarea 
              v-model="editDescValue"
              rows="2"
              class="w-full px-3 py-2 border border-primary-300 dark:border-zinc-800 focus:ring-1 focus:ring-zinc-900 rounded-sm text-sm bg-white dark:bg-gray-950 text-gray-800 dark:text-gray-100"
              placeholder="介绍该模块整体用途，供 Supervisor 智能分步调度选择。"
            ></textarea>

            <div class="flex items-center justify-end gap-2 pt-1 border-t border-gray-100 dark:border-gray-800/50">
              <button 
                class="px-2.5 py-1 text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1 border border-gray-200 dark:border-gray-700 rounded-sm"
                @click="editingDesc = false"
              >
                <X :size="12" />
                <span>取消</span>
              </button>
              <button 
                class="px-3 py-1 text-xs bg-green-600 text-white hover:bg-green-700 flex items-center gap-1 rounded-sm disabled:opacity-50"
                :disabled="savingDesc"
                @click="handleSaveDesc"
              >
                <Loader2 v-if="savingDesc" :size="12" class="animate-spin" />
                <Check v-else :size="12" />
                <span>保存修改</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 第三行：运行说明 -->
        <p class="text-[11px] text-gray-400 dark:text-gray-500 mt-1">
          * 提示：当前工具列表来自于本地 PostgreSQL 缓存。若要在执行任务时极速响应，请勿频繁强制刷新。
        </p>
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        <div v-if="loadingTools" class="text-center text-sm text-gray-400 dark:text-gray-500 py-12 flex flex-col items-center justify-center gap-3">
          <Loader2 :size="24" class="animate-spin text-primary-500" />
          <span>正在读取工具列表缓存...</span>
        </div>

        <div v-else-if="toolError" class="p-4 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-sm text-sm">
          <div class="font-semibold mb-1">连接失败</div>
          <div>{{ toolError }}</div>
        </div>

        <div v-else-if="activeTools.length === 0" class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
          该 Server 没有缓存任何工具，或者没有暴露任何工具。
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="t in activeTools"
            :key="t.name"
            class="bg-white dark:bg-zinc-900/40 rounded-xl p-5 shadow-sm hover:shadow-md hover:-translate-y-0.5 ring-1 ring-black/[0.03] dark:ring-white/[0.05] transition-all duration-300"
          >
            <div class="flex items-center gap-2 mb-3">
              <span class="font-mono text-xs font-bold text-zinc-700 dark:text-zinc-300 bg-zinc-100 dark:bg-zinc-800 px-2.5 py-1 rounded-md tracking-tight">{{ t.name }}</span>
            </div>
            <p class="text-sm text-zinc-600 dark:text-zinc-400 mb-4 leading-relaxed">{{ t.description || '(无描述)' }}</p>
            <details class="text-[11px] group">
              <summary class="cursor-pointer text-zinc-400 dark:text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300 font-medium select-none flex items-center gap-1.5 transition-colors">
                <span class="opacity-60 group-open:rotate-90 transition-transform text-[9px]">▶</span>
                输入 Schema
              </summary>
              <pre class="mt-3 p-3 bg-zinc-50 dark:bg-zinc-950/50 rounded-lg overflow-x-auto text-zinc-600 dark:text-zinc-400 font-mono text-[10px] ring-1 ring-inset ring-zinc-200/50 dark:ring-zinc-800/50 shadow-inner">{{ JSON.stringify(t.inputSchema, null, 2) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.animate-spin {
  animation: spin 1.2s linear infinite;
}
</style>
