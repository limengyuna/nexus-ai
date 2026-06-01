<script setup lang="ts">
/**
 * MCP 配置管理页面
 *
 * 管理外部 MCP Server 连接，并能从数据库直接查看每个 Server 暴露的工具清单（极速无感）。
 */
import { onMounted, ref } from 'vue'
import { CheckCircle2, Loader2, Plug, Plus, RefreshCw, Trash2, XCircle, Zap, Sparkles, Edit3, Check, X } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import type { MCPConnectionTestResult, MCPServerConfig, MCPToolInfo, MCPTransportType } from '@/api/mcp'
import * as mcpApi from '@/api/mcp'
import { useConfirm } from '@/composables/useConfirm'

const { confirm } = useConfirm()

const servers = ref<MCPServerConfig[]>([])
const activeServerId = ref<number | null>(null)
const activeView = ref<'list' | 'details'>('list')
const activeTools = ref<MCPToolInfo[]>([])
const loadingTools = ref(false)
const toolError = ref('')

// 编辑描述相关的响应式状态
const editingDesc = ref(false)
const editDescValue = ref('')
const savingDesc = ref(false)
const generatingEditDesc = ref(false)

const showCreateModal = ref(false)
const createForm = ref({
  name: '',
  description: '',
  transport_type: 'stdio' as MCPTransportType,
  connection_uri: '',
  env_vars_text: '',
})

onMounted(async () => {
  await fetchServers()
  if (servers.value.length > 0) {
    activeView.value = 'list'
  }
})

async function fetchServers() {
  servers.value = await mcpApi.listMcpServers()
  if (servers.value.length > 0 && !activeServerId.value) {
    await selectServer(servers.value[0].id)
    activeView.value = 'list'
  }
}

async function selectServer(id: number) {
  activeServerId.value = id
  activeView.value = 'details'
  activeTools.value = []
  toolError.value = ''
  loadingTools.value = true
  editingDesc.value = false // 切换 Server 时退出编辑模式
  
  // 查找本地的 Server 详情
  const s = servers.value.find((item) => item.id === id)
  if (s) {
    editDescValue.value = s.description || ''
  }

  if (s && s.cached_tools && s.cached_tools.length > 0) {
    // 优先加载 DB 缓存，0ms 极速响应
    activeTools.value = s.cached_tools
    loadingTools.value = false
    return
  }

  // 缓存为空，则去拉取
  try {
    activeTools.value = await mcpApi.listMcpTools(id)
    // 重新获取列表更新缓存状态
    servers.value = await mcpApi.listMcpServers()
  } catch (e: any) {
    toolError.value = e?.message || '连接外部 Server 失败'
  } finally {
    loadingTools.value = false
  }
}

// 总结/编辑 MCP 的描述
async function handleSaveDesc() {
  if (!activeServerId.value) return
  savingDesc.value = true
  try {
    const updated = await mcpApi.updateMcpServer(activeServerId.value, {
      description: editDescValue.value,
    })
    
    // 同步更新本地服务器列表数据
    const idx = servers.value.findIndex((s) => s.id === activeServerId.value)
    if (idx !== -1) {
      servers.value[idx].description = updated.description
    }
    editingDesc.value = false
    toast.success('整体描述更新成功')
  } catch (e: any) {
    toast.error(`更新描述失败: ${e?.message ?? '未知错误'}`)
  } finally {
    savingDesc.value = false
  }
}

async function handleRegenerateEditDesc() {
  if (!activeServerId.value) return
  generatingEditDesc.value = true
  try {
    const s = servers.value.find((item) => item.id === activeServerId.value)
    const res = await mcpApi.generateMcpDescription({
      server_name: s?.name || '外部 MCP',
      tools: activeTools.value,
    })
    editDescValue.value = res.description
    toast.success('AI 描述总结成功，请确认后保存')
  } catch (e: any) {
    toast.error(`AI 总结描述失败: ${e?.message ?? '未知错误'}`)
  } finally {
    generatingEditDesc.value = false
  }
}

// 手动强制重新连接刷新
const refreshing = ref(false)
async function handleRefreshCache() {
  if (!activeServerId.value) return
  refreshing.value = true
  toolError.value = ''
  try {
    activeTools.value = await mcpApi.refreshMcpTools(activeServerId.value)
    // 同步刷新本地服务器列表的缓存数据
    servers.value = await mcpApi.listMcpServers()
    toast.success('外部工具列表缓存已刷新')
  } catch (e: any) {
    toolError.value = e?.message || '刷新失败'
  } finally {
    refreshing.value = false
  }
}

// 连接测试状态
const testing = ref(false)
const testResult = ref<MCPConnectionTestResult | null>(null)
const generatingDesc = ref(false)

function parseEnvVars(): Record<string, string> | undefined {
  if (!createForm.value.env_vars_text.trim()) return undefined
  try {
    return JSON.parse(createForm.value.env_vars_text)
  } catch {
    toast.error('env_vars 必须是合法 JSON')
    return null as any  // 返回 null 表示出错（区别于 undefined 表示未填）
  }
}

async function handleTest() {
  if (!createForm.value.connection_uri.trim()) {
    toast.error('请先填写连接 URI')
    return
  }
  const envVars = parseEnvVars()
  if (envVars === null) return  // env_vars JSON 解析失败

  testing.value = true
  testResult.value = null
  try {
    testResult.value = await mcpApi.testMcpConnection({
      transport_type: createForm.value.transport_type,
      connection_uri: createForm.value.connection_uri,
      env_vars: envVars,
    })
    if (testResult.value.ok) {
      toast.success(`连接成功！发现 ${testResult.value.tools_count} 个工具（${testResult.value.latency_ms}ms）`)
      // 自动触发一次描述生成，也可以手动点击
      await handleGenerateDescription()
    } else {
      toast.error(`连接失败：${testResult.value.error}`)
    }
  } catch (e: any) {
    toast.error(`测试请求失败: ${e?.message ?? '未知错误'}`)
  } finally {
    testing.value = false
  }
}

// 调用 LLM 为这个 MCP 模块生成一个总的描述文案
async function handleGenerateDescription() {
  if (!testResult.value || !testResult.value.ok || testResult.value.tools_detail.length === 0) return
  generatingDesc.value = true
  try {
    const res = await mcpApi.generateMcpDescription({
      server_name: createForm.value.name || '外部 MCP',
      tools: testResult.value.tools_detail,
    })
    createForm.value.description = res.description
  } catch (e: any) {
    console.error('LLM 生成描述失败:', e)
  } finally {
    generatingDesc.value = false
  }
}

async function handleCreate() {
  if (!createForm.value.name.trim() || !createForm.value.connection_uri.trim()) {
    toast.error('请填写名称和连接 URI')
    return
  }

  let envVars: Record<string, string> | undefined
  if (createForm.value.env_vars_text.trim()) {
    try {
      envVars = JSON.parse(createForm.value.env_vars_text)
    } catch {
      toast.error('env_vars 必须是合法 JSON')
      return
    }
  }

  // 必须先经过成功的连接测试，或者强制提示
  if (!testResult.value || !testResult.value.ok) {
    const skipTest = await confirm({
      title: '未进行或连接测试失败',
      message: '我们强烈建议在创建前先完成“测试连接”，以便我们自动发现子工具并写入本地缓存，供系统极速运行。直接创建可能会在首次使用时导致卡顿。确定继续吗？',
      confirmText: '强制创建',
      variant: 'danger',
    })
    if (!skipTest) return
  }

  try {
    await mcpApi.createMcpServer({
      name: createForm.value.name,
      description: createForm.value.description || undefined,
      transport_type: createForm.value.transport_type,
      connection_uri: createForm.value.connection_uri,
      env_vars: envVars,
      cached_tools: testResult.value?.tools_detail || undefined,
      tool_count: testResult.value?.tools_count || 0,
    })
    showCreateModal.value = false
    createForm.value = { name: '', description: '', transport_type: 'stdio', connection_uri: '', env_vars_text: '' }
    testResult.value = null
    await fetchServers()
    toast.success('MCP Server 创建成功')
  } catch (e: any) {
    toast.error(`创建失败: ${e?.message ?? '未知错误'}`)
  }
}

async function handleDelete(id: number) {
  const target = servers.value.find((s) => s.id === id)
  const ok = await confirm({
    title: '删除 MCP Server',
    message: `确定删除“${target?.name ?? '该配置'}”吗？不会影响外部 MCP Server 本身，仅移除本系统连接配置。`,
    confirmText: '删除',
    variant: 'danger',
  })
  if (!ok) return
  try {
    await mcpApi.deleteMcpServer(id)
    if (activeServerId.value === id) {
      activeServerId.value = null
      activeTools.value = []
    }
    await fetchServers()
    toast.success('MCP 配置已删除')
  } catch (e: any) {
    toast.error(`删除失败: ${e?.message ?? '未知错误'}`)
  }
}

function transportColor(t: string): string {
  if (t === 'stdio') return 'bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700'
  if (t === 'sse') return 'bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700'
  return 'bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700'
}
</script>

<template>
  <div class="flex h-full bg-white dark:bg-zinc-950">
    <!-- 左侧 Server 列表 -->
    <div 
      class="w-full md:w-80 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col flex-shrink-0"
      :class="{'hidden md:flex': activeServerId !== null && activeView === 'details'}"
    >
      <div class="p-3 border-b border-gray-200 dark:border-gray-800">
        <button
          class="w-full py-2 px-3 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-sm hover:bg-zinc-800 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 dark:text-zinc-900 flex items-center justify-center gap-1.5"
          @click="showCreateModal = true"
        >
          <Plus :size="16" :stroke-width="2.5" />
          <span>新建 MCP Server</span>
        </button>
      </div>

      <div class="flex-1 overflow-y-auto p-2 space-y-1">
        <div v-if="servers.length === 0" class="text-center text-sm text-gray-400 py-8">
          暂无外部 MCP 配置
        </div>
        <div
          v-for="s in servers"
          :key="s.id"
          class="group p-3 rounded-sm cursor-pointer transition-colors"
          :class="activeServerId === s.id ? 'bg-zinc-200/50 dark:bg-zinc-800/50' : 'hover:bg-gray-100 dark:hover:bg-gray-800'"
          @click="selectServer(s.id)"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium text-gray-800 dark:text-gray-100 truncate flex items-center gap-1.5">
                <span class="truncate">{{ s.name }}</span>
                <span v-if="s.tool_count > 0" class="flex-shrink-0 px-1 py-0.2 text-[10px] bg-zinc-100 text-zinc-700 border border-zinc-200 rounded dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700">
                  {{ s.tool_count }} 工具
                </span>
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-2">
                <span class="px-1.5 py-0.5 rounded text-xs" :class="transportColor(s.transport_type)">
                  {{ s.transport_type }}
                </span>
                <span class="truncate">{{ s.connection_uri }}</span>
              </div>
            </div>
            <button
              class="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
              @click.stop="handleDelete(s.id)"
            >
              <Trash2 :size="14" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：工具清单 -->
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
            @click="activeView = 'list'"
            class="md:hidden flex items-center gap-1.5 text-xs text-zinc-700 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-800 rounded px-2.5 py-1.5 self-start active:scale-95 transition-transform bg-zinc-50 dark:bg-zinc-900"
          >
            ← 返回服务器列表
          </button>
          <!-- 第一行：服务名 & 强制刷新 -->
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="text-xl font-bold text-gray-900 dark:text-gray-100">
                {{ servers.find(s => s.id === activeServerId)?.name }}
              </h2>
              <span class="px-2 py-0.5 text-xs bg-zinc-100 text-zinc-700 border border-zinc-200 rounded-full dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700 font-medium">
                {{ activeTools.length }} 个工具已预缓存
              </span>
            </div>
            <button 
              class="text-xs text-zinc-900 dark:text-zinc-100 dark:text-zinc-100 hover:text-zinc-900 dark:text-zinc-100 dark:hover:text-primary-300 flex items-center justify-center gap-1.5 py-1.5 px-2.5 border border-zinc-200 dark:border-zinc-800 rounded-sm hover:bg-zinc-100 dark:hover:bg-primary-900/10 disabled:opacity-50 self-start sm:self-center"
              :disabled="refreshing"
              @click="handleRefreshCache"
            >
              <RefreshCw :size="12" :stroke-width="2.5" :class="refreshing ? 'animate-spin' : ''" />
              <span>{{ refreshing ? '重新连接刷新中...' : '强制连接外部刷新工具' }}</span>
            </button>
          </div>

          <!-- 第二行：整体描述展示与编辑 -->
          <div class="bg-gray-50 dark:bg-gray-900/60 rounded-md p-3.5 border border-gray-100 dark:border-gray-800/80">
            <!-- 默认展示状态 -->
            <div v-if="!editingDesc" class="flex items-start justify-between gap-4 group">
              <div class="flex-1 min-w-0">
                <span class="block text-xs font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider mb-1">
                  Supervisor 调度大纲描述 (Description)
                </span>
                <p 
                  v-if="servers.find(s => s.id === activeServerId)?.description" 
                  class="text-sm text-gray-700 dark:text-gray-300 leading-relaxed font-normal"
                >
                  {{ servers.find(s => s.id === activeServerId)?.description }}
                </p>
                <p v-else class="text-sm text-gray-400 dark:text-gray-500 italic">
                  (暂无大纲描述。推荐添加描述，以便 Supervisor 准确地拆解子步骤并调度该服务)
                </p>
              </div>
              <button 
                class="flex-shrink-0 flex items-center gap-1 text-xs text-zinc-900 dark:text-zinc-100 dark:text-zinc-100 hover:text-zinc-900 dark:text-zinc-100 font-medium bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 rounded-sm px-2.5 py-1"
                @click="editingDesc = true; editDescValue = servers.find(s => s.id === activeServerId)?.description || ''"
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
                  class="text-xs text-zinc-900 dark:text-zinc-100 hover:text-zinc-900 dark:text-zinc-100 flex items-center gap-1 disabled:opacity-50"
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
                  class="px-3 py-1 text-xs bg-green-600 text-white dark:text-zinc-900 hover:bg-green-700 flex items-center gap-1 rounded-sm disabled:opacity-50"
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
              class="border border-gray-200 dark:border-gray-700 rounded-sm p-4 hover:shadow-sm transition-shadow"
            >
              <div class="flex items-center gap-2 mb-2">
                <span class="font-mono text-sm font-semibold text-zinc-700 dark:text-zinc-300">{{ t.name }}</span>
              </div>
              <p class="text-sm text-gray-600 dark:text-gray-300 mb-3">{{ t.description || '(无描述)' }}</p>
              <details class="text-xs">
                <summary class="cursor-pointer text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200">输入 schema</summary>
                <pre class="mt-2 p-2 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded overflow-x-auto text-gray-700 dark:text-gray-200">{{ JSON.stringify(t.inputSchema, null, 2) }}</pre>
              </details>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>

  <!-- 新建 MCP Server 弹窗 -->
  <div
    v-if="showCreateModal"
    class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    @click.self="showCreateModal = false"
  >
    <div class="bg-white dark:bg-gray-900 rounded-md shadow-sm border border-zinc-200 dark:border-zinc-800 p-6 w-[34rem] space-y-3 max-h-[90vh] overflow-y-auto">
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">新建 MCP Server 连接</h3>

      <div class="grid grid-cols-2 gap-3">
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">名称 *</label>
          <input v-model="createForm.name" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-sm text-sm" placeholder="如: FileSystem" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-700 mb-1">传输方式</label>
          <select v-model="createForm.transport_type" class="w-full px-3 py-2 border border-gray-300 rounded-sm text-sm bg-white">
            <option value="stdio">stdio（本地命令）</option>
            <option value="sse">sse（远程 HTTP）</option>
          </select>
        </div>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">
          连接 URI *
          <span class="text-gray-400 ml-1 font-normal">
            {{ createForm.transport_type === 'stdio' ? '示例: npx -y @modelcontextprotocol/server-filesystem /tmp' : '示例: http://example.com/sse' }}
          </span>
        </label>
        <input v-model="createForm.connection_uri" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-sm text-sm font-mono" />
      </div>

      <div v-if="createForm.transport_type === 'stdio'">
        <label class="block text-xs font-medium text-gray-700 mb-1">环境变量（可选 JSON）</label>
        <textarea
          v-model="createForm.env_vars_text"
          rows="2"
          placeholder='例：{"GITHUB_TOKEN": "ghp_xxx"}'
          class="w-full px-3 py-2 border border-gray-300 rounded-sm text-sm font-mono"
        ></textarea>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1 flex items-center justify-between">
          <span>整体描述</span>
          <span v-if="generatingDesc" class="text-[10px] text-gray-400 flex items-center gap-1">
            <Loader2 :size="10" class="animate-spin" />
            AI 正在精简提炼描述中...
          </span>
          <button 
            v-else-if="testResult && testResult.ok && testResult.tools_detail.length > 0"
            class="text-[10px] text-zinc-900 dark:text-zinc-100 hover:text-zinc-900 dark:text-zinc-100 flex items-center gap-0.5"
            @click="handleGenerateDescription"
          >
            <Sparkles :size="10" />
            🪄 用 AI 生成描述
          </button>
        </label>
        <textarea 
          v-model="createForm.description" 
          rows="2" 
          class="w-full px-3 py-2 border border-gray-300 rounded-sm text-sm"
          placeholder="介绍该模块整体用途，供 Supervisor 智能分步调度选择。推荐利用 AI 生成以保证准确性。"
        ></textarea>
      </div>

      <!-- 测试连接结果卡片 -->
      <div
        v-if="testResult"
        class="rounded-sm p-3 text-xs border"
        :class="testResult.ok
          ? 'bg-zinc-50 border-zinc-200 text-zinc-800 dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-200'
          : 'bg-zinc-50 border-zinc-200 text-zinc-800 dark:bg-zinc-900 dark:border-zinc-700 dark:text-zinc-200'"
      >
        <div class="flex items-center gap-2 font-medium">
          <CheckCircle2 v-if="testResult.ok" :size="14" />
          <XCircle v-else :size="14" />
          <span>{{ testResult.ok ? '连接成功' : '连接失败' }}</span>
          <span class="ml-auto text-gray-500">{{ testResult.latency_ms }}ms</span>
        </div>
        <div v-if="testResult.ok" class="mt-1.5 text-gray-700">
          发现 <b>{{ testResult.tools_count }}</b> 个工具，已经为你写入预缓存。
          <div class="mt-1 flex flex-wrap gap-1">
            <span v-for="t in testResult.tools_detail.slice(0, 10)" :key="t.name" class="px-1.5 py-0.5 bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700 rounded text-[10px]">
              {{ t.name }}
            </span>
            <span v-if="testResult.tools_count > 10" class="text-[10px] text-gray-400">及其他 {{ testResult.tools_count - 10 }} 个...</span>
          </div>
        </div>
        <div v-else class="mt-1.5 break-all text-red-700">
          {{ testResult.error }}
        </div>
      </div>

      <!-- 按钮区 -->
      <div class="flex items-center gap-2 pt-2 border-t border-gray-100 dark:border-gray-800">
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-700 border border-gray-300 rounded-sm hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="testing || !createForm.connection_uri.trim()"
          title="连接外部 Server，并自动预拉取工具列表"
          @click="handleTest"
        >
          <Loader2 v-if="testing" :size="14" class="animate-spin" />
          <Zap v-else :size="14" />
          <span>{{ testing ? '拉取测试中...' : '测试连接并发现子工具' }}</span>
        </button>

        <div class="flex-1"></div>

        <button class="px-4 py-1.5 text-sm text-gray-600" @click="showCreateModal = false; testResult = null">取消</button>
        <button class="px-4 py-1.5 text-sm bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 rounded-sm hover:bg-zinc-800 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 dark:text-zinc-900" @click="handleCreate">
          创建并预缓存
        </button>
      </div>
    </div>
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
