<script setup lang="ts">
import { Plus, Trash2 } from 'lucide-vue-next'
import type { MCPServerConfig } from '@/api/mcp'
import { useConfirm } from '@/composables/useConfirm'

const props = defineProps<{
  servers: MCPServerConfig[]
  activeServerId: number | null
  activeView: 'list' | 'details'
}>()

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'show-create'): void
  (e: 'delete', id: number): void
}>()

const { confirm } = useConfirm()

async function handleDelete(id: number) {
  const target = props.servers.find((s) => s.id === id)
  const ok = await confirm({
    title: '删除 MCP Server',
    message: `确定删除“${target?.name ?? '该配置'}”吗？不会影响外部 MCP Server 本身，仅移除本系统连接配置。`,
    confirmText: '删除',
    variant: 'danger',
  })
  if (!ok) return
  emit('delete', id)
}

function transportColor(t: string): string {
  if (t === 'stdio') return 'bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700'
  if (t === 'sse') return 'bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700'
  return 'bg-zinc-100 text-zinc-700 border border-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:border-zinc-700'
}
</script>

<template>
  <div 
    class="w-full md:w-80 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col flex-shrink-0"
    :class="{'hidden md:flex': activeServerId !== null && activeView === 'details'}"
  >
    <div class="p-4 flex-shrink-0">
      <button
        class="w-full py-2.5 px-3 bg-transparent text-zinc-600 dark:text-zinc-400 text-sm font-medium rounded-xl hover:bg-zinc-100 dark:hover:bg-zinc-800/50 hover:text-zinc-900 dark:hover:text-zinc-200 border border-dashed border-zinc-300 dark:border-zinc-700 transition-all duration-200 flex items-center justify-center gap-2"
        @click="$emit('show-create')"
      >
        <Plus :size="15" :stroke-width="2.5" />
        <span>添加 MCP Server</span>
      </button>
    </div>

    <div class="flex-1 overflow-y-auto px-3 pb-3 space-y-2">
      <div v-if="servers.length === 0" class="text-center text-sm text-gray-400 py-8">
        暂无外部 MCP 配置
      </div>
      <div
        v-for="s in servers"
        :key="s.id"
        class="group p-3.5 rounded-xl cursor-pointer transition-all duration-200"
        :class="activeServerId === s.id ? 'bg-white dark:bg-zinc-800 shadow-sm ring-1 ring-black/[0.04] dark:ring-white/[0.05]' : 'hover:bg-zinc-200/50 dark:hover:bg-zinc-800/40'"
        @click="$emit('select', s.id)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium text-gray-800 dark:text-gray-100 truncate flex items-center gap-1.5">
              <span class="truncate">{{ s.name }}</span>
              <span v-if="s.tool_count > 0" class="flex-shrink-0 px-1.5 py-0.5 text-[9px] font-mono bg-zinc-100 dark:bg-zinc-900 text-zinc-500 dark:text-zinc-400 rounded uppercase tracking-wide">
                {{ s.tool_count }} 工具
              </span>
            </div>
            <div class="text-[11px] text-zinc-500 dark:text-zinc-400 mt-1.5 flex items-center gap-2">
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
</template>
