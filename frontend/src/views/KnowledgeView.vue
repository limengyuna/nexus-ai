<script setup lang="ts">
/**
 * 知识库管理页面
 *
 * 左侧 KB 列表，右侧选中 KB 的文档列表 + 上传
 */
import { computed, onMounted, ref } from 'vue'
import { Eye, FileText, Info, Loader2, Pencil, Plus, RotateCcw, Search, Trash2, Upload, X } from 'lucide-vue-next'
import { toast } from 'vue-sonner'

import * as kbApi from '@/api/knowledge'
import type { ChunkPreview, DocumentItem, KnowledgeBase, TaskRecord } from '@/api/knowledge'
import SkeletonList from '@/components/SkeletonList.vue'
import { useConfirm } from '@/composables/useConfirm'
import { useKnowledgeStore } from '@/stores/knowledge'

const { confirm } = useConfirm()

const kb = useKnowledgeStore()
const activeKbId = ref<number | null>(null)

const showCreateModal = ref(false)
const createForm = ref({
  name: '',
  description: '',
  chunk_strategy: 'recursive' as 'recursive' | 'markdown' | 'semantic',
  enable_llm_clean: false,
})

const fileInput = ref<HTMLInputElement | null>(null)
const uploadingFiles = ref<{ name: string; progress: number; status: string; error?: string }[]>([])

// 编辑弹窗
const showEditModal = ref(false)
const editForm = ref({
  name: '',
  description: '',
})

const activeKb = computed<KnowledgeBase | null>(() =>
  kb.knowledgeBases.find((k) => k.id === activeKbId.value) ?? null,
)

// 文档搜索过滤
const docSearchKeyword = ref('')
const filteredDocuments = computed(() => {
  const kw = docSearchKeyword.value.trim().toLowerCase()
  if (!kw) return kb.documents
  return kb.documents.filter((d) => d.file_name.toLowerCase().includes(kw))
})

// 批量上传进度统计
const uploadStats = computed(() => {
  const total = uploadingFiles.value.length
  const success = uploadingFiles.value.filter((f) => f.status === 'success' || f.status === 'completed').length
  const failed = uploadingFiles.value.filter((f) => f.status === 'failed').length
  const inProgress = total - success - failed
  return { total, success, failed, inProgress }
})

// ---------- 文档分块预览弹窗 ----------
const showChunksModal = ref(false)
const chunksLoading = ref(false)
const chunksDoc = ref<DocumentItem | null>(null)
const chunksList = ref<ChunkPreview[]>([])

async function openChunksPreview(doc: DocumentItem) {
  if (!activeKbId.value) return
  if (doc.status !== 'completed') {
    toast.error('该文档尚未处理完成，暂无分块可预览')
    return
  }
  chunksDoc.value = doc
  showChunksModal.value = true
  chunksLoading.value = true
  chunksList.value = []
  try {
    const resp = await kbApi.listDocumentChunks(activeKbId.value, doc.id)
    chunksList.value = resp.chunks
  } catch (e: any) {
    toast.error(`加载分块失败: ${e?.message ?? '未知错误'}`)
  } finally {
    chunksLoading.value = false
  }
}

function closeChunksPreview() {
  showChunksModal.value = false
  chunksDoc.value = null
  chunksList.value = []
}

function openEditModal() {
  if (!activeKb.value) return
  editForm.value = {
    name: activeKb.value.name,
    description: activeKb.value.description ?? '',
  }
  showEditModal.value = true
}

async function handleSaveEdit() {
  if (!activeKb.value || !editForm.value.name.trim()) return
  try {
    await kb.updateKnowledgeBase(activeKb.value.id, {
      name: editForm.value.name.trim(),
      description: editForm.value.description.trim() || undefined,
    })
    showEditModal.value = false
    toast.success('保存成功')
  } catch (e: any) {
    toast.error(`更新失败: ${e?.message ?? '未知错误'}`)
  }
}

onMounted(async () => {
  await kb.fetchKnowledgeBases()
  if (kb.knowledgeBases.length > 0) {
    await selectKb(kb.knowledgeBases[0].id)
  }
})

async function selectKb(id: number) {
  activeKbId.value = id
  await kb.fetchDocuments(id)
}

async function handleCreate() {
  if (!createForm.value.name.trim()) {
    toast.error('请填写知识库名称')
    return
  }
  try {
    const created = await kb.createKnowledgeBase({ ...createForm.value })
    showCreateModal.value = false
    createForm.value = { name: '', description: '', chunk_strategy: 'recursive', enable_llm_clean: false }
    await selectKb(created.id)
    toast.success(`知识库“${created.name}”创建成功`)
  } catch (e: any) {
    toast.error(`创建失败: ${e?.message ?? '未知错误'}`)
  }
}

async function handleDeleteKb(id: number) {
  const target = kb.knowledgeBases.find((k) => k.id === id)
  const ok = await confirm({
    title: '删除知识库',
    message: `确定删除“${target?.name ?? '该知识库'}”吗？所有文档与向量数据会被同时清除，不可恢复。`,
    confirmText: '删除',
    variant: 'danger',
  })
  if (!ok) return
  try {
    await kb.deleteKnowledgeBase(id)
    if (activeKbId.value === id) {
      activeKbId.value = kb.knowledgeBases[0]?.id ?? null
      if (activeKbId.value) await kb.fetchDocuments(activeKbId.value)
    }
    toast.success('知识库已删除')
  } catch (e: any) {
    toast.error(`删除失败: ${e?.message ?? '未知错误'}`)
  }
}

function triggerFileSelect() {
  fileInput.value?.click()
}

// ---------- 上传策略选择弹窗 ----------
// 用户选完文件先弹窗选策略（'default' 表示沿用 KB 默认）；确认后才真正开始上传
const showUploadStrategyModal = ref(false)
const pendingUploadFiles = ref<File[]>([])
const pendingUploadStrategy = ref<'default' | 'recursive' | 'markdown' | 'semantic'>('default')
// LLM 清洗三态：'default' 沿用 KB 默认；'on' 显式开启；'off' 显式关闭
const pendingUploadLlmClean = ref<'default' | 'on' | 'off'>('default')

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (!target.files || !activeKbId.value) return
  const files = Array.from(target.files)
  // 重置 input 以便同名文件可重复上传
  target.value = ''
  if (files.length === 0) return

  // 暂存文件并打开策略选择弹窗
  pendingUploadFiles.value = files
  pendingUploadStrategy.value = 'default'
  pendingUploadLlmClean.value = 'default'
  showUploadStrategyModal.value = true
}

async function confirmUploadWithStrategy() {
  if (!activeKbId.value || pendingUploadFiles.value.length === 0) {
    showUploadStrategyModal.value = false
    return
  }
  const files = pendingUploadFiles.value
  // 'default' 不传策略 → 后端沿用 KB 默认；否则按用户选择覆盖
  const strategyOverride =
    pendingUploadStrategy.value === 'default' ? undefined : pendingUploadStrategy.value
  // LLM 清洗三态：default → undefined（沿用 KB），on → true，off → false
  const llmCleanOverride =
    pendingUploadLlmClean.value === 'default'
      ? undefined
      : pendingUploadLlmClean.value === 'on'
  // 关闭弹窗并清理暂存
  showUploadStrategyModal.value = false
  pendingUploadFiles.value = []

  for (const file of files) {
    const trackItem: { name: string; progress: number; status: string; error?: string } = { name: file.name, progress: 0, status: 'pending' }
    uploadingFiles.value.push(trackItem)
    try {
      await kb.uploadDocument(
        activeKbId.value,
        file,
        (task: TaskRecord) => {
          trackItem.progress = task.progress
          trackItem.status = task.status
        },
        strategyOverride,
        llmCleanOverride,
      )
    } catch (e: any) {
      trackItem.status = 'failed'
      trackItem.error = e?.message
    } finally {
      // 刷新文档列表
      await kb.fetchDocuments(activeKbId.value)
      // 1.5s 后从进度列表移除已成功的
      setTimeout(() => {
        if (trackItem.status === 'success') {
          uploadingFiles.value = uploadingFiles.value.filter((f) => f !== trackItem)
        }
      }, 1500)
    }
  }
  // 刷新 KB 列表以更新 document_count
  await kb.fetchKnowledgeBases()
}

function cancelUploadStrategy() {
  showUploadStrategyModal.value = false
  pendingUploadFiles.value = []
}

async function handleReprocessDoc(doc: DocumentItem) {
  if (!activeKbId.value) return
  const ok = await confirm({
    title: '重新处理文档',
    message: `将清除"${doc.file_name}"已有分块/向量，并按当前知识库的分块策略重新处理。是否继续？`,
    confirmText: '重新处理',
  })
  if (!ok) return
  try {
    await kbApi.reprocessDocument(activeKbId.value, doc.id)
    await kb.fetchDocuments(activeKbId.value)
    toast.success('已重新投递处理，请等待进度变化')
  } catch (e: any) {
    toast.error(`重新处理失败: ${e?.message ?? '未知错误'}`)
  }
}

async function handleDeleteDoc(docId: number) {
  const doc = kb.documents.find((d) => d.id === docId)
  const ok = await confirm({
    title: '删除文档',
    message: `确定删除“${doc?.file_name ?? '该文档'}”吗？文档与其向量数据会一并删除。`,
    confirmText: '删除',
    variant: 'danger',
  })
  if (!ok) return
  if (!activeKbId.value) return
  try {
    await kb.deleteDocument(activeKbId.value, docId)
    await kb.fetchKnowledgeBases()
    toast.success('文档已删除')
  } catch (e: any) {
    toast.error(`删除失败: ${e?.message ?? '未知错误'}`)
  }
}

function fileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function statusColor(s: string): string {
  if (s === 'completed' || s === 'success') return 'text-green-700 bg-green-100'
  if (s === 'failed') return 'text-red-700 bg-red-100'
  if (s === 'pending') return 'text-gray-600 bg-gray-100'
  return 'text-blue-700 bg-blue-100'
}

function statusLabel(s: string): string {
  const m: Record<string, string> = {
    pending: '等待中',
    parsing: '解析中',
    chunking: '分块中',
    embedding: '向量化',
    completed: '完成',
    failed: '失败',
    running: '处理中',
    success: '完成',
  }
  return m[s] || s
}
</script>

<template>
  <div class="flex h-full">
    <!-- 左侧：KB 列表 -->
    <div class="w-72 bg-gray-50 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-800 flex flex-col">
      <div class="p-3 border-b border-gray-200 dark:border-gray-800">
        <button
          class="w-full py-2 px-3 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 flex items-center justify-center gap-1.5"
          @click="showCreateModal = true"
        >
          <Plus :size="16" :stroke-width="2.5" />
          <span>新建知识库</span>
        </button>
      </div>
      <div class="flex-1 overflow-y-auto p-2 space-y-1">
        <SkeletonList
          v-if="kb.loading && kb.knowledgeBases.length === 0"
          :rows="4"
          item-class="h-16 w-full"
          class="px-1"
        />
        <div v-else-if="kb.knowledgeBases.length === 0" class="text-center text-sm text-gray-400 py-8">
          暂无知识库
        </div>
        <div
          v-for="k in kb.knowledgeBases"
          :key="k.id"
          class="group p-3 rounded-lg cursor-pointer transition-colors"
          :class="activeKbId === k.id ? 'bg-primary-100 dark:bg-primary-900/40' : 'hover:bg-gray-100 dark:hover:bg-gray-800'"
          @click="selectKb(k.id)"
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
              @click.stop="handleDeleteKb(k.id)"
            >
              <Trash2 :size="14" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 右侧：文档管理 -->
    <div class="flex-1 flex flex-col bg-white dark:bg-gray-950">
      <div v-if="!activeKb" class="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
        请选择或创建一个知识库
      </div>

      <template v-else>
        <!-- 头部 -->
        <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-800">
          <div class="flex items-start justify-between gap-3">
            <div class="min-w-0 flex-1">
              <h2 class="text-lg font-semibold text-gray-800 dark:text-gray-100 truncate">{{ activeKb.name }}</h2>
              <p v-if="activeKb.description" class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ activeKb.description }}</p>
            </div>
            <button
              class="text-xs text-gray-500 dark:text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors flex items-center gap-1 px-2 py-1 rounded-md hover:bg-gray-100 dark:hover:bg-gray-800 flex-shrink-0"
              title="编辑名称/描述"
              @click="openEditModal"
            >
              <Pencil :size="12" :stroke-width="2" />
              <span>编辑</span>
            </button>
          </div>
          <div class="flex gap-4 mt-2 text-xs text-gray-500 dark:text-gray-400">
            <span>策略: <span class="font-medium text-gray-700 dark:text-gray-200">{{ activeKb.chunk_strategy }}</span></span>
            <span>chunk_size: <span class="font-medium text-gray-700 dark:text-gray-200">{{ activeKb.chunk_size }}</span></span>
            <span>overlap: <span class="font-medium text-gray-700 dark:text-gray-200">{{ activeKb.chunk_overlap }}</span></span>
          </div>
        </div>

        <!-- 上传区 -->
        <div class="px-6 py-3 border-b border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900">
          <button
            class="px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 flex items-center gap-2"
            @click="triggerFileSelect"
          >
            <Upload :size="16" :stroke-width="2" />
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
                  :class="f.status === 'failed' ? 'bg-red-500' : 'bg-primary-500'"
                  :style="{ width: `${f.progress}%` }"
                ></div>
              </div>
              <span class="px-2 py-0.5 rounded text-xs" :class="statusColor(f.status)">
                {{ statusLabel(f.status) }} {{ f.progress }}%
              </span>
            </div>
          </div>
        </div>

        <!-- 文档列表 -->
        <div class="flex-1 overflow-y-auto px-6 py-4">
          <!-- 文档搜索（仅文档 > 5 时显示，否则浪费视觉空间）-->
          <div v-if="kb.documents.length > 5" class="mb-3 relative max-w-sm">
            <Search :size="14" class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              v-model="docSearchKeyword"
              type="text"
              placeholder="按文件名搜索..."
              class="w-full pl-9 pr-8 py-1.5 text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 border border-gray-200 dark:border-gray-700 rounded-md focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            />
            <button
              v-if="docSearchKeyword"
              class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              @click="docSearchKeyword = ''"
            >
              <X :size="14" />
            </button>
          </div>

          <table v-if="filteredDocuments.length > 0" class="w-full text-sm">
            <thead>
              <tr class="text-left text-xs text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-800">
                <th class="py-2 pr-3 font-medium">文件名</th>
                <th class="py-2 pr-3 font-medium">类型</th>
                <th class="py-2 pr-3 font-medium">大小</th>
                <th class="py-2 pr-3 font-medium">分块数</th>
                <th class="py-2 pr-3 font-medium">状态</th>
                <th class="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(d, idx) in kb.documents"
                :key="d.id"
                class="border-b border-gray-100 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900/50"
              >
                <td class="py-2.5 pr-3 text-gray-800 dark:text-gray-200 truncate max-w-xs">{{ d.file_name }}</td>
                <td class="py-2.5 pr-3 text-gray-600 dark:text-gray-300 uppercase">{{ d.file_type }}</td>
                <td class="py-2.5 pr-3 text-gray-600 dark:text-gray-300">{{ fileSize(d.file_size) }}</td>
                <td class="py-2.5 pr-3 text-gray-600 dark:text-gray-300">{{ d.chunk_count }}</td>
                <td class="py-2.5 pr-3">
                  <span class="px-2 py-0.5 rounded text-xs font-medium" :class="statusColor(d.status)">
                    {{ statusLabel(d.status) }}
                  </span>
                </td>
                <td class="py-2.5 text-right">
                  <div class="flex items-center justify-end gap-2">
                    <button
                      class="flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600 disabled:opacity-40 disabled:hover:text-gray-500 disabled:cursor-not-allowed"
                      :disabled="d.status !== 'completed'"
                      :title="d.status === 'completed' ? '查看分块预览' : '文档尚未处理完成'"
                      @click="openChunksPreview(d)"
                    >
                      <Eye :size="13" />
                      <span>预览</span>
                    </button>
                    <button
                      v-if="d.status === 'failed' || d.status === 'completed'"
                      class="flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600"
                      :title="d.status === 'failed' ? '上次处理失败，点击重试' : '按当前策略重新切分'"
                      @click="handleReprocessDoc(d)"
                    >
                      <RotateCcw :size="13" />
                      <span>{{ d.status === 'failed' ? '重试' : '重新处理' }}</span>
                    </button>
                    <button
                      class="text-xs text-gray-400 hover:text-red-500"
                      @click="handleDeleteDoc(d.id)"
                    >
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
            还没有文档，点击上方按钮上传
          </div>
        </div>
      </template>
    </div>
  </div>

  <!-- 创建知识库弹窗 -->
  <div
    v-if="showCreateModal"
    class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    @click.self="showCreateModal = false"
  >
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 w-[28rem] space-y-3">
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">新建知识库</h3>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">名称 *</label>
        <input
          v-model="createForm.name"
          type="text"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">描述</label>
        <textarea
          v-model="createForm.description"
          rows="2"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        ></textarea>
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">分块策略</label>
        <select
          v-model="createForm.chunk_strategy"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value="recursive">recursive（通用递归字符切分）</option>
          <option value="markdown">markdown（按标题层级切分，保留语义结构）</option>
          <option value="semantic">semantic（基于 Embedding 语义跳变切分，适合无明确结构的长文本，较慢）</option>
        </select>
      </div>

      <!-- LLM 文档清洗开关（可选预处理层） -->
      <div class="flex items-start gap-2 p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-700/50 rounded-lg">
        <input
          id="enable-llm-clean"
          v-model="createForm.enable_llm_clean"
          type="checkbox"
          class="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label for="enable-llm-clean" class="flex-1 text-xs text-gray-700 dark:text-gray-300 cursor-pointer">
          <span class="font-medium block mb-0.5">启用 LLM 文档清洗（实验性）</span>
          <span class="text-gray-500 dark:text-gray-400 leading-relaxed">
            上传时额外调用 LLM 将格式混乱的 PDF 重排为标准 Markdown，提升分块质量。
            含 5 道防线防止内容被篡改。仅对本知识库生效，会增加 token 消耗和上传处理时间。
          </span>
        </label>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button class="px-4 py-1.5 text-sm text-gray-600" @click="showCreateModal = false">取消</button>
        <button
          class="px-4 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          @click="handleCreate"
        >
          创建
        </button>
      </div>
    </div>
  </div>

  <!-- 编辑知识库弹窗（仅改名称/描述） -->
  <div
    v-if="showEditModal"
    class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    @click.self="showEditModal = false"
  >
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 w-[28rem] space-y-3">
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">编辑知识库</h3>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">名称 *</label>
        <input
          v-model="editForm.name"
          type="text"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          @keydown.enter="handleSaveEdit"
        />
      </div>

      <div>
        <label class="block text-xs font-medium text-gray-700 mb-1">描述</label>
        <textarea
          v-model="editForm.description"
          rows="3"
          class="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
        ></textarea>
      </div>

      <div class="text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-800 px-3 py-2 rounded-lg flex items-start gap-2">
        <Info :size="14" :stroke-width="2" class="flex-shrink-0 mt-0.5 text-gray-400 dark:text-gray-500" />
        <span>提示：分块策略创建后不可修改（已上传的文档不会按新策略重新切分）。如确需更换，建议新建一个知识库重新上传。</span>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button class="px-4 py-1.5 text-sm text-gray-600" @click="showEditModal = false">取消</button>
        <button
          class="px-4 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed"
          :disabled="!editForm.name.trim()"
          @click="handleSaveEdit"
        >
          保存
        </button>
      </div>
    </div>
  </div>

  <!-- 上传文档：分块策略选择弹窗 -->
  <!-- 选完文件后弹出此弹窗，允许为本次上传的所有文件统一选择一个分块策略；不选则沿用 KB 默认 -->
  <div
    v-if="showUploadStrategyModal"
    class="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
    @click.self="cancelUploadStrategy"
  >
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-xl p-6 w-[30rem] space-y-3">
      <h3 class="text-lg font-semibold text-gray-800 dark:text-gray-100">选择分块策略</h3>
      <p class="text-xs text-gray-500 dark:text-gray-400">
        将为以下 <span class="font-medium text-gray-700 dark:text-gray-200">{{ pendingUploadFiles.length }}</span> 个文件统一应用分块策略。<br />
        不同类型的文档建议使用不同策略以获得更好的检索效果。
      </p>

      <!-- 文件列表（折叠展示，最多 3 行） -->
      <div class="max-h-24 overflow-y-auto bg-gray-50 dark:bg-gray-800/60 rounded-lg p-2 space-y-1 text-xs text-gray-600 dark:text-gray-300">
        <div v-for="f in pendingUploadFiles" :key="f.name" class="truncate" :title="f.name">
          · {{ f.name }}
        </div>
      </div>

      <!-- 分块策略单选 -->
      <div class="space-y-1">
        <div class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">分块策略</div>
        <label
          v-for="opt in [
            { value: 'default', title: '沿用知识库默认', desc: '使用当前知识库创建时设置的分块策略' },
            { value: 'recursive', title: 'recursive', desc: '通用递归字符切分，适用于任何文档（兜底）' },
            { value: 'markdown', title: 'markdown', desc: '按 # 标题层级切分，保留语义结构（推荐论文、法律、技术文档）' },
            { value: 'semantic', title: 'semantic', desc: '基于 Embedding 语义跳变切分，适合无明确标题的长文本（如对话、小说），较慢' },
          ]"
          :key="opt.value"
          class="flex items-start gap-2 p-2.5 rounded-lg border border-gray-200 dark:border-gray-700 cursor-pointer hover:border-primary-400 dark:hover:border-primary-600 transition-colors"
          :class="{ 'border-primary-500 bg-primary-50 dark:bg-primary-900/20': pendingUploadStrategy === opt.value }"
        >
          <input
            v-model="pendingUploadStrategy"
            type="radio"
            :value="opt.value"
            class="mt-0.5 h-4 w-4 text-primary-600 focus:ring-primary-500"
          />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-gray-800 dark:text-gray-100">{{ opt.title }}</div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ opt.desc }}</div>
          </div>
        </label>
      </div>

      <!-- LLM 清洗三态 -->
      <div class="space-y-1 pt-1">
        <div class="text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">
          LLM 文档清洗
          <span class="text-gray-400 dark:text-gray-500 font-normal">（实验性 · 提升伪 Markdown 结构识别）</span>
        </div>
        <div class="flex gap-2">
          <label
            v-for="opt in [
              { value: 'default', title: '沿用知识库默认' },
              { value: 'on', title: '启用' },
              { value: 'off', title: '禁用' },
            ]"
            :key="opt.value"
            class="flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg border border-gray-200 dark:border-gray-700 cursor-pointer hover:border-primary-400 dark:hover:border-primary-600 transition-colors text-xs"
            :class="{ 'border-primary-500 bg-primary-50 dark:bg-primary-900/20 font-medium text-primary-700 dark:text-primary-300': pendingUploadLlmClean === opt.value }"
          >
            <input
              v-model="pendingUploadLlmClean"
              type="radio"
              :value="opt.value"
              class="h-3.5 w-3.5 text-primary-600 focus:ring-primary-500"
            />
            <span>{{ opt.title }}</span>
          </label>
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button class="px-4 py-1.5 text-sm text-gray-600" @click="cancelUploadStrategy">取消</button>
        <button
          class="px-4 py-1.5 text-sm bg-primary-600 text-white rounded-lg hover:bg-primary-700"
          @click="confirmUploadWithStrategy"
        >
          开始上传
        </button>
      </div>
    </div>
  </div>

  <!-- 文档分块预览弹窗 -->
  <div
    v-if="showChunksModal"
    class="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
    @click.self="closeChunksPreview"
  >
    <div class="bg-white dark:bg-gray-900 rounded-2xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col">
      <!-- 头部 -->
      <div class="px-5 py-4 border-b border-gray-200 dark:border-gray-800 flex items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <h3 class="text-base font-semibold text-gray-800 dark:text-gray-100 flex items-center gap-2">
            <FileText :size="16" class="text-primary-600 flex-shrink-0" />
            <span class="truncate" :title="chunksDoc?.file_name">{{ chunksDoc?.file_name }}</span>
          </h3>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">
            <span v-if="!chunksLoading">共 {{ chunksList.length }} 个分块 · 策略 {{ activeKb?.chunk_strategy }}</span>
            <span v-else>正在加载...</span>
          </p>
        </div>
        <button
          class="p-1.5 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-md transition-colors flex-shrink-0"
          @click="closeChunksPreview"
        >
          <X :size="18" />
        </button>
      </div>

      <!-- 内容区 -->
      <div class="flex-1 overflow-y-auto px-5 py-4">
        <div v-if="chunksLoading" class="flex flex-col items-center justify-center py-12 text-gray-400 dark:text-gray-500">
          <Loader2 :size="32" class="animate-spin mb-3" />
          <span class="text-sm">正在加载分块数据...</span>
        </div>

        <div v-else-if="chunksList.length === 0" class="text-center text-sm text-gray-400 dark:text-gray-500 py-12">
          该文档没有分块数据
        </div>

        <div v-else class="space-y-3">
          <div
            v-for="(c, idx) in chunksList"
            :key="c.chunk_id"
            class="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden hover:border-primary-300 dark:hover:border-primary-700 transition-colors"
          >
            <div class="px-3 py-2 bg-gray-50 dark:bg-gray-800 flex items-center justify-between border-b border-gray-200 dark:border-gray-700">
              <span class="text-xs font-mono text-gray-600 dark:text-gray-300">
                #{{ idx + 1 }}
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

      <!-- 底部 -->
      <div class="px-5 py-3 border-t border-gray-200 dark:border-gray-800 flex justify-end">
        <button
          class="px-4 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200"
          @click="closeChunksPreview"
        >
          关闭
        </button>
      </div>
    </div>
  </div>
</template>
