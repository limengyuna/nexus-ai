<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { FileText, Search, X, Loader2 } from 'lucide-vue-next'
import { toast } from 'vue-sonner'
import * as kbApi from '@/api/knowledge'
import type { DocumentItem, ChunkPreview } from '@/api/knowledge'

const props = defineProps<{
  kbId: number
  document: DocumentItem
  fallbackStrategy: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const chunksLoading = ref(false)
const chunksList = ref<ChunkPreview[]>([])

// 分页与搜索响应式状态
const chunksLimit = ref(50)
const chunksCurrentPage = ref(1)
const chunksTotalCount = ref(0)
const chunksSearchKeyword = ref('')

async function loadChunksData() {
  chunksLoading.value = true
  chunksList.value = []
  
  const offset = (chunksCurrentPage.value - 1) * chunksLimit.value
  try {
    const resp = await kbApi.listDocumentChunks(props.kbId, props.document.id, {
      limit: chunksLimit.value,
      offset: offset,
      keyword: chunksSearchKeyword.value.trim() || undefined,
    })
    chunksList.value = resp.chunks
    chunksTotalCount.value = resp.total
  } catch (e: any) {
    toast.error(`加载分块失败: ${e?.message ?? '未知错误'}`)
  } finally {
    chunksLoading.value = false
  }
}

onMounted(() => {
  loadChunksData()
})

async function changeChunkPage(page: number) {
  const totalPages = Math.ceil(chunksTotalCount.value / chunksLimit.value)
  if (page < 1 || page > totalPages || chunksLoading.value) return
  chunksCurrentPage.value = page
  await loadChunksData()
}

async function handleChunkSearch() {
  chunksCurrentPage.value = 1
  await loadChunksData()
}

async function clearChunkSearch() {
  chunksSearchKeyword.value = ''
  chunksCurrentPage.value = 1
  await loadChunksData()
}
</script>

<template>
  <div
    class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
    @click.self="$emit('close')"
  >
    <div class="bg-white dark:bg-gray-900 rounded-md shadow-lg border border-zinc-200 dark:border-zinc-800 w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden">
      <!-- 头部 -->
      <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-center justify-between gap-4">
        <div class="min-w-0 flex-1">
          <h3 class="text-base font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
            <FileText :size="16" class="text-zinc-900 dark:text-zinc-100 flex-shrink-0" />
            <span class="truncate max-w-[14rem] sm:max-w-[20rem]" :title="document.file_name">{{ document.file_name }}</span>
          </h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            <span>策略: <span class="font-medium text-gray-700 dark:text-gray-300">{{ document.chunk_strategy || fallbackStrategy }}</span></span>
            <span class="mx-1.5">·</span>
            <span>匹配分块: <span class="font-medium text-gray-700 dark:text-gray-300">{{ chunksTotalCount }}</span></span>
          </p>
        </div>

        <!-- 弹窗内部关键字过滤搜索框 -->
        <div class="relative w-44 sm:w-56 flex-shrink-0">
          <Search :size="13" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            v-model="chunksSearchKeyword"
            type="text"
            placeholder="搜索文本分块并回车..."
            class="w-full pl-8 pr-7 py-1.5 text-xs bg-gray-50 dark:bg-gray-800 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-700 rounded-sm focus:outline-none focus:ring-2 focus:ring-zinc-900 focus:border-transparent transition-all"
            @keydown.enter="handleChunkSearch"
          />
          <button
            v-if="chunksSearchKeyword"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
            @click="clearChunkSearch"
          >
            <X :size="12" />
          </button>
        </div>

        <button
          class="p-1.5 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors flex-shrink-0"
          @click="$emit('close')"
        >
          <X :size="18" />
        </button>
      </div>

      <!-- 内容区 -->
      <div class="flex-1 min-h-0 overflow-y-auto pl-5 pr-2 py-4 custom-scrollbar">
        <div v-if="chunksLoading" class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
          <Loader2 :size="32" class="animate-spin mb-3" />
          <span class="text-sm">正在加载分块数据...</span>
        </div>

        <div v-else-if="chunksList.length === 0" class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
          暂无匹配的分块数据
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="(c, idx) in chunksList"
            :key="c.chunk_id"
            class="border border-gray-200 dark:border-gray-700 rounded-sm overflow-hidden hover:border-primary-300 dark:hover:border-primary-700 transition-colors"
          >
            <div class="px-3 py-2 bg-gray-50 dark:bg-gray-800 flex items-center justify-between border-b border-gray-200 dark:border-gray-700">
              <span class="text-xs font-mono text-gray-600 dark:text-gray-300">
                #{{ (chunksCurrentPage - 1) * chunksLimit + idx + 1 }}
                <span v-if="c.metadata?.header_path" class="ml-2 text-blue-600 dark:text-blue-400">
                  📑 {{ c.metadata.header_path }}
                </span>
                <span v-if="c.metadata?.parent_content" class="ml-2 px-1.5 py-0.5 bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-400 rounded text-[10px] font-medium">
                  子块
                </span>
              </span>
              <span class="text-xs text-gray-400 dark:text-gray-500">{{ c.content.length }} 字符</span>
            </div>
            <pre class="px-3 py-2.5 text-xs text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap break-words font-sans bg-white dark:bg-gray-900">{{ c.content }}</pre>
            
            <!-- Parent 完整内容（可折叠） -->
            <details v-if="c.metadata?.parent_content" class="border-t border-gray-100 dark:border-gray-800">
              <summary class="px-3 py-1.5 text-[11px] text-amber-600 dark:text-amber-400 cursor-pointer hover:bg-amber-50 dark:hover:bg-amber-900/20 select-none">
                查看完整父块（{{ c.metadata.parent_content.length }} 字符）
              </summary>
              <pre class="px-3 py-2 text-xs text-gray-500 dark:text-gray-400 leading-relaxed whitespace-pre-wrap break-words font-sans bg-amber-50/50 dark:bg-amber-900/10">{{ c.metadata.parent_content }}</pre>
            </details>
          </div>
        </div>
      </div>

      <!-- 翻页与操作栏 -->
      <div class="px-5 py-3 border-t border-gray-200 dark:border-gray-800 bg-gray-50/50 dark:bg-gray-900/20 bg-white dark:bg-zinc-950 flex items-center justify-between">
        <!-- 左侧：分页状态 -->
        <div class="text-xs text-gray-500 dark:text-gray-400">
          <span v-if="chunksTotalCount > 0">
            第 <span class="font-semibold text-gray-700 dark:text-gray-200">{{ chunksCurrentPage }}</span> 页 / 共 {{ Math.ceil(chunksTotalCount / chunksLimit) }} 页 (共 {{ chunksTotalCount }} 个分块)
          </span>
          <span v-else-if="!chunksLoading">暂无数据</span>
        </div>

        <!-- 中间：翻页操作 -->
        <div v-if="chunksTotalCount > chunksLimit" class="flex items-center gap-1.5">
          <button
            class="px-2.5 py-1 text-xs border border-gray-200 dark:border-gray-700 rounded-md text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-800 disabled:opacity-40 disabled:hover:bg-transparent transition-colors"
            :disabled="chunksCurrentPage === 1 || chunksLoading"
            @click="changeChunkPage(chunksCurrentPage - 1)"
          >
            上一页
          </button>
          <button
            class="px-2.5 py-1 text-xs border border-gray-200 dark:border-gray-700 rounded-md text-gray-600 dark:text-gray-300 hover:bg-white dark:hover:bg-gray-800 disabled:opacity-40 disabled:hover:bg-transparent transition-colors"
            :disabled="chunksCurrentPage >= Math.ceil(chunksTotalCount / chunksLimit) || chunksLoading"
            @click="changeChunkPage(chunksCurrentPage + 1)"
          >
            下一页
          </button>
        </div>

        <!-- 右侧：关闭 -->
        <button
          class="px-4 py-1.5 text-xs bg-gray-100 hover:bg-gray-200 dark:bg-gray-800 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-200 font-medium rounded-sm transition-colors"
          @click="$emit('close')"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 8px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background-color: rgba(156, 163, 175, 0.45);
  border-radius: 9999px;
  border: 2px solid transparent;
  background-clip: padding-box;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background-color: rgba(156, 163, 175, 0.75);
}
</style>
