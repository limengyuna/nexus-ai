<script setup lang="ts">
import { Plus, Trash2 } from 'lucide-vue-next'
import type { KnowledgeBase } from '@/api/knowledge'
import SkeletonList from '@/components/SkeletonList.vue'

const props = defineProps<{
  knowledgeBases: KnowledgeBase[]
  loading: boolean
  activeKbId: number | null
  activeView: 'list' | 'details'
}>()

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'delete', id: number): void
  (e: 'create'): void
}>()
</script>

<template>
  <div 
    class="w-full md:w-72 bg-zinc-50/50 dark:bg-zinc-900/30 border-r border-zinc-200/60 dark:border-zinc-800 flex flex-col flex-shrink-0"
    :class="{'hidden md:flex': activeKbId !== null && activeView === 'details'}"
  >
    <div class="p-4 border-b border-zinc-200/60 dark:border-zinc-800">
      <button
        class="w-full py-2.5 px-3 bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 text-sm font-medium rounded-xl hover:bg-black dark:hover:bg-white shadow-sm transition-all flex items-center justify-center gap-1.5"
        @click="$emit('create')"
      >
        <Plus :size="16" :stroke-width="2.5" />
        <span>新建知识库</span>
      </button>
    </div>
    <div class="flex-1 overflow-y-auto p-2 space-y-1">
      <SkeletonList
        v-if="loading && knowledgeBases.length === 0"
        :rows="4"
        item-class="h-16 w-full"
        class="px-1"
      />
      <div v-else-if="knowledgeBases.length === 0" class="text-center text-sm text-gray-400 py-8">
        暂无知识库
      </div>
      <div
        v-for="k in knowledgeBases"
        :key="k.id"
        class="group p-3 rounded-xl cursor-pointer transition-colors"
        :class="activeKbId === k.id ? 'bg-white dark:bg-zinc-800 shadow-sm border border-zinc-200/60 dark:border-zinc-700' : 'hover:bg-zinc-100 dark:hover:bg-zinc-800/50 border border-transparent'"
        @click="$emit('select', k.id)"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0 flex-1">
            <div class="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">{{ k.name }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              {{ k.document_count }} 个文档 · {{ k.chunk_strategy }}
            </div>
          </div>
          <button
            class="text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100"
            @click.stop="$emit('delete', k.id)"
          >
            <Trash2 :size="14" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
