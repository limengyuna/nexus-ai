<script setup lang="ts">
import { ref } from 'vue'
import { Loader2, Zap, Sparkles, CheckCircle2, XCircle } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import * as mcpApi from '@/api/mcp'
import type { MCPConnectionTestResult, MCPTransportType } from '@/api/mcp'
import { useConfirm } from '@/composables/useConfirm'

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'created'): void
}>()

const { confirm } = useConfirm()

const createForm = ref({
  name: '',
  description: '',
  transport_type: 'stdio' as MCPTransportType,
  connection_uri: '',
  env_vars_text: '',
})

const testing = ref(false)
const testResult = ref<MCPConnectionTestResult | null>(null)
const generatingDesc = ref(false)

function parseEnvVars(): Record<string, string> | undefined {
  if (!createForm.value.env_vars_text.trim()) return undefined
  try {
    return JSON.parse(createForm.value.env_vars_text)
  } catch {
    toast.error('env_vars 必须是合法 JSON')
    return null as any  // 返回 null 表示出错
  }
}

async function handleTest() {
  if (!createForm.value.connection_uri.trim()) {
    toast.error('请先填写连接 URI')
    return
  }
  const envVars = parseEnvVars()
  if (envVars === null) return

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
      // 自动触发一次描述生成
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

  const envVars = parseEnvVars()
  if (envVars === null) return

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
    toast.success('MCP Server 创建成功')
    emit('created')
  } catch (e: any) {
    toast.error(`创建失败: ${e?.message ?? '未知错误'}`)
  }
}
</script>

<template>
  <div
    class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    @click.self="$emit('close')"
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
            class="text-[10px] text-zinc-900 dark:text-zinc-100 hover:text-zinc-900 flex items-center gap-0.5"
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

        <button class="px-4 py-1.5 text-sm text-gray-600" @click="$emit('close')">取消</button>
        <button class="px-4 py-1.5 text-sm bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 rounded-sm hover:bg-zinc-800 dark:hover:bg-zinc-200" @click="handleCreate">
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
