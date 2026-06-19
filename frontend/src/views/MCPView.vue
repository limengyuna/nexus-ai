<script setup lang="ts">
/**
 * MCP 配置管理页面 (McpView.vue) - 重构壳组件
 *
 * 管理外部 MCP Server 连接，组件职责已分离为：
 * 1. McpSidebar：左侧列表和删除逻辑
 * 2. McpToolsDetail：右侧的工具清单、Schema 预览和 AI 大纲描述维护
 * 3. McpCreateModal：复杂的新建连接测试流程
 */
import { onMounted, ref, computed } from 'vue'
import { toast } from 'vue-sonner'

import type { MCPServerConfig, MCPToolInfo } from '@/api/mcp'
import * as mcpApi from '@/api/mcp'

// 引入拆解后的子组件
import McpSidebar from '@/components/mcp/McpSidebar.vue'
import McpToolsDetail from '@/components/mcp/McpToolsDetail.vue'
import McpCreateModal from '@/components/mcp/McpCreateModal.vue'

const servers = ref<MCPServerConfig[]>([])
const activeServerId = ref<number | null>(null)
const activeView = ref<'list' | 'details'>('list')

const activeTools = ref<MCPToolInfo[]>([])
const loadingTools = ref(false)
const toolError = ref('')
const refreshing = ref(false)

const showCreateModal = ref(false)

// 计算当前选中的服务器配置（传递给右侧详情页）
const currentServer = computed(() => servers.value.find(s => s.id === activeServerId.value))

onMounted(async () => {
  await fetchServers()
  if (servers.value.length > 0) {
    activeView.value = 'list'
  }
})

// 拉取服务器列表
async function fetchServers() {
  servers.value = await mcpApi.listMcpServers()
  if (servers.value.length > 0 && !activeServerId.value) {
    await selectServer(servers.value[0].id)
    activeView.value = 'list'
  }
}

// 选中某个 Server 并尝试加载缓存工具
async function selectServer(id: number) {
  activeServerId.value = id
  activeView.value = 'details'
  activeTools.value = []
  toolError.value = ''
  loadingTools.value = true

  const s = servers.value.find((item) => item.id === id)

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

// 在 Sidebar 中删除 Server 后的回调
function handleServerDeleted(id: number) {
  if (activeServerId.value === id) {
    activeServerId.value = null
    activeTools.value = []
  }
  fetchServers()
}

// 手动强制重新连接刷新当前 Server 的缓存
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

// 在 Detail 中修改大纲后的同步回调
function handleDescUpdated(updatedDesc: string) {
  const idx = servers.value.findIndex((s) => s.id === activeServerId.value)
  if (idx !== -1) {
    servers.value[idx].description = updatedDesc
  }
}
</script>

<template>
  <div class="flex h-full bg-white dark:bg-zinc-950">
    <!-- 左侧 Server 列表 -->
    <McpSidebar 
      :servers="servers"
      :active-server-id="activeServerId"
      :active-view="activeView"
      @select="selectServer"
      @delete="handleServerDeleted"
      @show-create="showCreateModal = true"
    />

    <!-- 右侧工具清单和详情 -->
    <McpToolsDetail 
      :server="currentServer"
      :active-server-id="activeServerId"
      :active-view="activeView"
      :active-tools="activeTools"
      :loading-tools="loadingTools"
      :tool-error="toolError"
      :refreshing="refreshing"
      @back="activeView = 'list'"
      @refresh-cache="handleRefreshCache"
      @desc-updated="handleDescUpdated"
    />

    <!-- 新建连接测试弹窗 -->
    <McpCreateModal 
      v-if="showCreateModal" 
      @close="showCreateModal = false"
      @created="showCreateModal = false; fetchServers()"
    />
  </div>
</template>
