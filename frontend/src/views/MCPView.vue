<script setup lang="ts">
/**
 * MCP 配置管理页面
 *
 * 管理外部 MCP Server 连接，并能实时查看每个 Server 暴露的工具清单。
 */
import { onMounted, ref } from 'vue'
import { CheckCircle2, Loader2, Plug, Plus, RefreshCw, Trash2, XCircle, Zap } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import type { MCPConnectionTestResult, MCPServerConfig, MCPToolInfo, MCPTransportType } from '@/api/mcp'
import * as mcpApi from '@/api/mcp'
import { useConfirm } from '@/composables/useConfirm'

const { confirm } = useConfirm()

const servers = ref<MCPServerConfig[]>([])
const activeServerId = ref<number | null>(null)
const activeTools = ref<MCPToolInfo[]>([])
const loadingTools = ref(false)
const toolError = ref('')

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
})

async function fetchServers() {
  servers.value = await mcpApi.listMcpServers()
  if (servers.value.length > 0 && !activeServerId.value) {
    await selectServer(servers.value[0].id)
  }
}

async function selectServer(id: number) {
  activeServerId.value = id
  activeTools.value = []
  toolError.value = ''
  loadingTools.value = true
  try {
    activeTools.value = await mcpApi.listMcpTools(id)
  } catch (e: any) {
    toolError.value = e?.message || '连接外部 Server 失败'
  } finally {
    loadingTools.value = false
  }
}

// 连接测试状态
const testing = ref(false)
const testResult = ref<MCPConnectionTestResult | null>(null)

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
    } else {
      toast.error(`连接失败：${testResult.value.error}`)
    }
  } catch (e: any) {
    toast.error(`测试请求失败: ${e?.message ?? '未知错误'}`)
  } finally {
    testing.value = false
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

  try {
    await mcpApi.createMcpServer({
      name: createForm.value.name,
      description: createForm.value.description || undefined,
      transport_type: createForm.value.transport_type,
      connection_uri: createForm.value.connection_uri,
      env_vars: envVars,
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
  if (t === 'stdio') return 'bg-purple-100 text-purple-700'
  if (t === 'sse') return 'bg-blue-100 text-blue-700'
  return 'bg-gray-100 text-gray-700'
}
</script>

<template>
  <div class="flex h-full">
    <!-- 左侧 Server 列表 -->
    <div class="w-80 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col">
      <div class="p-3 border-b border-gray-200 dark:border-gray-800">
        <button
          class="w-full py-2 px-3 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 flex items-center justify-center gap-1.5"
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
          class="group p-3 rounded-lg cursor-pointer transition-colors"
          :class="activeServerId === s.id ? 'bg-primary-100 dark:bg-primary-900/40' : 'hover:bg-gray-100 dark:hover:bg-gray-800'"
          @click="selectServer(s.id)"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{{ s.name }}</div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 flex items-center gap-2">
                <span class="px-1.5 py-0.5 rounded text-xs" :class="transportColor(s.transport_type)">
                  {{ s.transport_type }}
                </span>
                <span class="truncate">{{ s.connection_uri }}</span>
              </div>
            </div>
            <button
              class="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100"
              @click.stop="handleDelete(s.id)"
            >
              <Trash2 :size="14" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：工具清单 -->
    <div class="flex-1 flex flex-col bg-white dark:bg-gray-950">
      <div v-if="!activeServerId" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
        请选择或新建一个 MCP Server
      </div>

      <template v-else>
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <div class="flex items-center justify-between">
            <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100">外部工具清单</h2>
            <button class="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 flex items-center gap-1" @click="selectServer(activeServerId!)">
              <RefreshCw :size="12" :stroke-width="2" />
              <span>刷新</span>
            </button>
          </div>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">实时从外部 MCP Server 拉取，Agent 可在 Tool Agent 节点中调用这些工具</p>
        </div>

        <div class="flex-1 overflow-y-auto p-6">
          <div v-if="loadingTools" class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
            正在连接外部 MCP Server...
          </div>

          <div v-else-if="toolError" class="p-4 bg-red-50 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-lg text-sm">
            <div class="font-semibold mb-1">连接失败</div>
            <div>{{ toolError }}</div>
          </div>

          <div v-else-if="activeTools.length === 0" class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
            该 Server 没有暴露任何工具
          </div>

          <div v-else class="space-y-3">
            <div
              v-for="t in activeTools"
              :key="t.name"
              class="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-sm transition-shadow"
            >
              <div class="flex items-center gap-2 mb-2">
                <span class="font-mono text-sm font-semibold text-purple-700 dark:text-purple-300">{{ t.name }}</span>
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
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 w-[32rem] space-y-3">
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">新建 MCP Server 连接</h3>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">名称 *</label>
        <input v-model="createForm.name" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">描述</label>
        <input v-model="createForm.description" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm" />
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">传输方式</label>
        <select v-model="createForm.transport_type" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white">
          <option value="stdio">stdio（本地子进程，如 npx 启动）</option>
          <option value="sse">sse（远程 HTTP Server-Sent Events）</option>
        </select>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">
          连接 URI *
          <span class="text-gray-400 ml-1 font-normal">
            {{ createForm.transport_type === 'stdio' ? '示例: npx -y @modelcontextprotocol/server-filesystem /tmp' : '示例: http://example.com/sse' }}
          </span>
        </label>
        <input v-model="createForm.connection_uri" type="text" class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono" />
      </div>

      <div v-if="createForm.transport_type === 'stdio'">
        <label class="block text-xs font-medium text-gray-700 mb-1">环境变量（可选 JSON）</label>
        <textarea
          v-model="createForm.env_vars_text"
          rows="3"
          placeholder='例：{"GITHUB_TOKEN": "ghp_xxx"}'
          class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm font-mono"
        ></textarea>
      </div>

      <!-- 测试连接结果卡片 -->
      <div
        v-if="testResult"
        class="rounded-lg p-3 text-xs border"
        :class="testResult.ok
          ? 'bg-green-50 border-green-200 text-green-800'
          : 'bg-red-50 border-red-200 text-red-800'"
      >
        <div class="flex items-center gap-2 font-medium">
          <CheckCircle2 v-if="testResult.ok" :size="14" />
          <XCircle v-else :size="14" />
          <span>{{ testResult.ok ? '连接成功' : '连接失败' }}</span>
          <span class="ml-auto text-gray-500">{{ testResult.latency_ms }}ms</span>
        </div>
        <div v-if="testResult.ok" class="mt-1.5 text-gray-700">
          发现 <b>{{ testResult.tools_count }}</b> 个工具<span v-if="testResult.tools.length"> · 预览: {{ testResult.tools.join(', ') }}</span>
        </div>
        <div v-else class="mt-1.5 break-all text-red-700">
          {{ testResult.error }}
        </div>
      </div>

      <!-- 按钮区 -->
      <div class="flex items-center gap-2 pt-2">
        <button
          class="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="testing || !createForm.connection_uri.trim()"
          title="临时连接外部 MCP Server，验证 URI 和 env_vars 是否正确"
          @click="handleTest"
        >
          <Loader2 v-if="testing" :size="14" class="animate-spin" />
          <Zap v-else :size="14" />
          <span>{{ testing ? '测试中...' : '测试连接' }}</span>
        </button>

        <div class="flex-1"></div>

        <button class="px-4 py-1.5 text-sm text-gray-600" @click="showCreateModal = false; testResult = null">取消</button>
        <button class="px-4 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700" @click="handleCreate">
          创建
        </button>
      </div>
    </div>
  </div>
</template>
