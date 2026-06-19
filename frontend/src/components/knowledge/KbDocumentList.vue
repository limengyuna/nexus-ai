<script setup lang="ts">
import { ref, computed } from 'vue'
import { Eye, Pencil, RotateCcw, Search, Trash2, Upload, X, Loader2 } from 'lucide-vue-next'
import type { KnowledgeBase, DocumentItem, DocumentStatus } from '@/api/knowledge'

const props = defineProps<{
  activeKb: KnowledgeBase | null
  documents: DocumentItem[]
  uploadingFiles: { name: string; progress: number; taskStatus: string; detailStatus: DocumentStatus | null; error?: string }[]
}>()

const emit = defineEmits<{
  (e: 'back'): void
  (e: 'edit'): void
  (e: 'upload', files: File[]): void
  (e: 'preview', doc: DocumentItem): void
  (e: 'reprocess', doc: DocumentItem): void
  (e: 'delete', id: number): void
}>()

const fileInput = ref<HTMLInputElement | null>(null)
const docSearchKeyword = ref('')

const filteredDocuments = computed(() => {
  const kw = docSearchKeyword.value.trim().toLowerCase()
  if (!kw) return props.documents
  return props.documents.filter((d) => d.file_name.toLowerCase().includes(kw))
})

const uploadStats = computed(() => {
  const total = props.uploadingFiles.length
  const success = props.uploadingFiles.filter((f) => f.taskStatus === 'success' || f.taskStatus === 'completed').length
  const failed = props.uploadingFiles.filter((f) => f.taskStatus === 'failed' || f.taskStatus === 'cancelled').length
  const inProgress = total - success - failed
  return { total, success, failed, inProgress }
})

function triggerFileSelect() {
  fileInput.value?.click()
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files || !props.activeKb) return
  const files = Array.from(target.files)
  target.value = ''
  if (files.length > 0) {
    emit('upload', files)
  }
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function statusColor(s: string): string {
  if (s === 'completed' || s === 'success') return 'text-emerald-700 bg-emerald-50 border border-emerald-200/50 dark:text-emerald-400 dark:bg-emerald-500/10 dark:border-emerald-500/20'
  if (s === 'failed' || s === 'cancelled') return 'text-rose-700 bg-rose-50 border border-rose-200/50 dark:text-rose-400 dark:bg-rose-500/10 dark:border-rose-500/20'
  if (s === 'pending') return 'text-zinc-500 bg-zinc-50 border border-zinc-200 dark:text-zinc-400 dark:bg-zinc-800/50 dark:border-zinc-700'
  return 'text-zinc-800 bg-zinc-100 border border-zinc-300/60 dark:text-zinc-200 dark:bg-zinc-800 dark:border-zinc-600/50 font-medium'
}

function statusLabel(s: string): string {
  const m: Record<string, string> = {
    pending: '等待后台任务执行',
    parsing: '正在读取和提取文本',
    cleaning: '正在优化文档结构，此步骤可能耗时较长',
    chunking: '正在进行语义分块',
    embedding: '正在调用模型进行向量化，此步骤通常最耗时',
    storing: '正在写入知识库',
    completed: '文档处理完成',
    failed: '文档处理失败',
    cancelled: '任务已取消',
    running: '处理中',
    success: '文档处理完成',
  }
  return m[s] || s
}

function displayStatus(f: { taskStatus: string; detailStatus: DocumentStatus | null }): string {
  if (['success', 'completed', 'failed', 'cancelled'].includes(f.taskStatus)) {
    return f.taskStatus
  }
  return f.detailStatus || f.taskStatus
}
</script>

<template>
  <div class="flex-grow flex flex-col bg-white dark:bg-gray-950">
    <div v-if="!activeKb" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
      请选择或创建一个知识库
    </div>

    <template v-else>
      <!-- 头部 -->
      <div class="px-8 py-6 border-b border-zinc-200/60 dark:border-zinc-800">
        <!-- 移动端返回按钮 -->
        <button
          @click="$emit('back')"
          class="md:hidden mb-4 flex items-center gap-1.5 text-xs text-zinc-700 dark:text-zinc-300 border border-zinc-200 dark:border-zinc-800 rounded px-2.5 py-1.5 self-start active:scale-95 transition-transform bg-zinc-50 dark:bg-zinc-900"
        >
          ← 返回知识库列表
        </button>

        <div class="flex items-start justify-between gap-3">
          <div class="min-w-0 flex-1">
            <h2 class="text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">{{ activeKb.name }}</h2>
            <p v-if="activeKb.description" class="text-sm text-zinc-500 dark:text-zinc-400 mt-1.5 leading-relaxed">{{ activeKb.description }}</p>
          </div>
          <button
            class="text-xs text-zinc-500 dark:text-zinc-400 hover:text-zinc-900 dark:text-zinc-100 dark:hover:text-white transition-colors flex items-center gap-1.5 px-3 py-1.5 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-800 flex-shrink-0 border border-transparent hover:border-zinc-200/60"
            title="编辑名称/描述"
            @click="$emit('edit')"
          >
            <Pencil :size="13" :stroke-width="2.5" />
            <span class="font-medium">编辑</span>
          </button>
        </div>
        <div class="flex gap-2.5 mt-3.5 text-xs text-zinc-600 dark:text-zinc-400">
          <span class="px-2.5 py-1 rounded-md bg-zinc-100/80 dark:bg-zinc-800/80 border border-zinc-200/60 dark:border-zinc-700">策略: <span class="font-mono font-semibold text-zinc-900 dark:text-zinc-200 ml-0.5">{{ activeKb.chunk_strategy }}</span></span>
          <span class="px-2.5 py-1 rounded-md bg-zinc-100/80 dark:bg-zinc-800/80 border border-zinc-200/60 dark:border-zinc-700">chunk_size: <span class="font-mono font-semibold text-zinc-900 dark:text-zinc-200 ml-0.5">{{ activeKb.chunk_size }}</span></span>
          <span class="px-2.5 py-1 rounded-md bg-zinc-100/80 dark:bg-zinc-800/80 border border-zinc-200/60 dark:border-zinc-700">overlap: <span class="font-mono font-semibold text-zinc-900 dark:text-zinc-200 ml-0.5">{{ activeKb.chunk_overlap }}</span></span>
        </div>
      </div>

      <!-- 上传区 -->
      <div class="px-8 py-4 border-b border-zinc-200/60 dark:border-zinc-800 bg-zinc-50/50 dark:bg-zinc-900/30 flex items-center justify-between">
        <button
          class="px-5 py-2.5 bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900 text-sm font-medium rounded-xl hover:bg-black dark:hover:bg-white shadow-sm transition-all flex items-center gap-2"
          @click="triggerFileSelect"
        >
          <Upload :size="16" :stroke-width="2.5" />
          <span>上传文档</span>
        </button>
        <input
          ref="fileInput"
          type="file"
          accept=".pdf,.docx,.doc,.md,.txt,.pptx,.ppt,.xlsx,.xls,.csv,.html,.htm,.xml,.json,.rtf,.odt"
          multiple
          class="hidden"
          @change="handleFileChange"
        />

        <!-- 上传进度（含批量统计）-->
        <div v-if="uploadingFiles.length > 0" class="mt-3 space-y-2">
          <!-- 批量统计摘要 -->
          <div v-if="uploadStats.total > 1" class="flex items-center gap-3 text-xs text-gray-600 dark:text-gray-300 pb-1 border-b border-gray-200 dark:border-gray-700">
            <span class="font-medium">批量上传：</span>
            <span>共 <b class="text-gray-800">{{ uploadStats.total }}</b> 个文件</span>
            <span class="text-blue-600">进行中 {{ uploadStats.inProgress }}</span>
            <span class="text-green-600">成功 {{ uploadStats.success }}</span>
            <span v-if="uploadStats.failed > 0" class="text-red-600">失败 {{ uploadStats.failed }}</span>
          </div>
          <!-- 单文件进度行 -->
          <div
            v-for="f in uploadingFiles"
            :key="f.name"
            class="flex items-center gap-3 text-xs"
          >
            <span class="truncate flex-1 text-gray-700 dark:text-gray-200" :title="f.name">{{ f.name }}</span>
            <div class="w-40 h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                class="h-full transition-all"
                :class="(f.taskStatus === 'failed' || f.taskStatus === 'cancelled') ? 'bg-red-500' : 'bg-zinc-900 dark:bg-zinc-100'"
                :style="{ width: `${f.progress}%` }"
              ></div>
            </div>
            <span class="px-2 py-0.5 rounded text-xs" :class="statusColor(displayStatus(f))">
              {{ statusLabel(displayStatus(f)) }} <span class="text-gray-400 ml-1">{{ f.progress }}%</span>
              <Loader2 v-if="!['success', 'completed', 'failed', 'cancelled'].includes(f.taskStatus)" class="inline-block ml-1 animate-spin" :size="12" />
            </span>
          </div>
        </div>
      </div>

      <!-- 文档列表 -->
      <div class="flex-1 overflow-y-auto px-8 py-6">
        <!-- 文档搜索 -->
        <div v-if="documents.length > 5" class="mb-4 relative max-w-sm">
          <Search :size="14" class="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            v-model="docSearchKeyword"
            type="text"
            placeholder="按文件名搜索..."
            class="w-full pl-10 pr-8 py-2 text-sm bg-white dark:bg-zinc-900 text-zinc-800 dark:text-zinc-200 border border-zinc-200 dark:border-zinc-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-zinc-900/50 dark:focus:ring-zinc-100/30 focus:border-zinc-900 dark:focus:border-zinc-100 transition-all"
          />
          <button
            v-if="docSearchKeyword"
            class="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-600"
            @click="docSearchKeyword = ''"
          >
            <X :size="14" />
          </button>
        </div>

        <table v-if="filteredDocuments.length > 0" class="hidden md:table w-full text-sm">
          <thead>
            <tr class="text-left text-xs text-zinc-500 dark:text-zinc-400 border-b border-zinc-200/60 dark:border-zinc-800">
              <th class="py-3 pr-3 font-medium">文件名</th>
              <th class="py-3 pr-3 font-medium">类型</th>
              <th class="py-3 pr-3 font-medium">大小</th>
              <th class="py-3 pr-3 font-medium">分块数</th>
              <th class="py-3 pr-3 font-medium">状态</th>
              <th class="py-3 font-medium text-right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="d in filteredDocuments"
              :key="d.id"
              class="border-b border-zinc-100/80 dark:border-zinc-800/60 hover:bg-zinc-50/50 dark:hover:bg-zinc-900/30 transition-colors group"
            >
              <td class="py-3.5 pr-3 text-zinc-800 dark:text-zinc-200 font-medium truncate max-w-[200px]">{{ d.file_name }}</td>
              <td class="py-3.5 pr-3 text-zinc-500 dark:text-zinc-400 text-xs font-mono uppercase">{{ d.file_type }}</td>
              <td class="py-3.5 pr-3 text-zinc-600 dark:text-zinc-400 font-mono text-xs">{{ fileSize(d.file_size) }}</td>
              <td class="py-3.5 pr-3 text-zinc-600 dark:text-zinc-400 font-mono text-xs">{{ d.chunk_count }}</td>
              <td class="py-3.5 pr-3">
                <span class="px-2 py-1 rounded-md text-xs font-semibold tracking-wide flex w-max items-center gap-1.5" :class="statusColor(d.status)">
                  <span v-if="['pending', 'parsing', 'cleaning', 'chunking', 'embedding', 'storing', 'running'].includes(d.status)" class="w-1.5 h-1.5 rounded-full bg-current animate-pulse"></span>
                  <span v-else-if="d.status === 'completed'" class="w-1.5 h-1.5 rounded-full bg-current"></span>
                  <span v-else-if="d.status === 'failed'" class="w-1.5 h-1.5 rounded-full bg-current"></span>
                  {{ statusLabel(d.status) }}
                </span>
              </td>
              <td class="py-3.5 text-right">
                <div class="flex items-center justify-end gap-1 opacity-60 group-hover:opacity-100 transition-opacity">
                  <button
                    class="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-900 hover:bg-zinc-100 dark:hover:bg-zinc-800/80 dark:hover:text-white disabled:opacity-40 disabled:hover:text-zinc-500 disabled:hover:bg-transparent transition-colors"
                    :disabled="d.status !== 'completed'"
                    :title="d.status === 'completed' ? '查看分块预览' : '文档尚未处理完成'"
                    @click="$emit('preview', d)"
                  >
                    <Eye :size="16" />
                  </button>
                  <button
                    v-if="d.status === 'failed' || d.status === 'completed'"
                    class="p-1.5 rounded-lg text-zinc-500 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/30 transition-colors"
                    :title="d.status === 'failed' ? '上次处理失败，点击重试' : '按当前策略重新切分'"
                    @click="$emit('reprocess', d)"
                  >
                    <RotateCcw :size="16" />
                  </button>
                  <button
                    class="p-1.5 rounded-lg text-zinc-400 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-900/30 transition-colors"
                    title="删除文档"
                    @click="$emit('delete', d.id)"
                  >
                    <Trash2 :size="16" />
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>

        <!-- 移动端卡片式流布局 -->
        <div v-if="filteredDocuments.length > 0" class="md:hidden space-y-3">
          <div
            v-for="d in filteredDocuments"
            :key="d.id"
            class="bg-zinc-50/50 dark:bg-zinc-900/30 border border-zinc-200/60 dark:border-zinc-800/80 rounded p-4 flex flex-col gap-2 hover:border-zinc-400 dark:hover:border-zinc-700 transition-all"
          >
            <div class="flex items-start justify-between gap-3">
              <span class="text-sm font-semibold text-zinc-800 dark:text-zinc-200 truncate flex-1" :title="d.file_name">
                {{ d.file_name }}
              </span>
              <span class="px-2 py-0.5 rounded text-[10px] font-semibold flex-shrink-0" :class="statusColor(d.status)">
                {{ statusLabel(d.status) }}
              </span>
            </div>

            <div class="flex items-center gap-3 text-xs text-zinc-500 dark:text-zinc-400">
              <span class="uppercase font-medium">{{ d.file_type }}</span>
              <span>·</span>
              <span>{{ fileSize(d.file_size) }}</span>
              <span>·</span>
              <span>{{ d.chunk_count }} 个分块</span>
            </div>

            <div class="flex items-center justify-end gap-3.5 pt-2.5 border-t border-zinc-100 dark:border-zinc-800/60 mt-1">
              <button
                class="flex items-center gap-1 text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100 disabled:opacity-40"
                :disabled="d.status !== 'completed'"
                @click="$emit('preview', d)"
              >
                <Eye :size="13" />
                <span>预览</span>
              </button>
              <button
                v-if="d.status === 'failed' || d.status === 'completed'"
                class="flex items-center gap-1 text-xs text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-zinc-100"
                @click="$emit('reprocess', d)"
              >
                <RotateCcw :size="13" />
                <span>重试/重新处理</span>
              </button>
              <button
                class="text-xs text-rose-500 hover:text-rose-600 font-semibold"
                @click="$emit('delete', d.id)"
              >
                删除
              </button>
            </div>
          </div>
        </div>
        <div v-else class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
          还没有文档，点击上方按钮上传
        </div>
      </div>
    </template>
  </div>
</template>
