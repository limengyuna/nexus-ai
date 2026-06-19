<script setup lang="ts">
/**
 * 知识库管理页面 (重构壳组件)
 *
 * 只负责状态路由与 API 派发，UI 逻辑已被拆解到 src/components/knowledge 下：
 * 1. KbSidebar
 * 2. KbDocumentList
 * 3. KbCreateModal / KbEditModal
 * 4. KbUploadStrategyModal / KbChunksPreviewModal
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { toast } from 'vue-sonner'

import * as kbApi from '@/api/knowledge'
import type { DocumentItem, DocumentStatus, KnowledgeBase, TaskRecord } from '@/api/knowledge'
import { useConfirm } from '@/composables/useConfirm'
import { useKnowledgeStore } from '@/stores/knowledge'

import KbSidebar from '@/components/knowledge/KbSidebar.vue'
import KbDocumentList from '@/components/knowledge/KbDocumentList.vue'
import KbCreateModal from '@/components/knowledge/KbCreateModal.vue'
import KbEditModal from '@/components/knowledge/KbEditModal.vue'
import KbUploadStrategyModal from '@/components/knowledge/KbUploadStrategyModal.vue'
import KbChunksPreviewModal from '@/components/knowledge/KbChunksPreviewModal.vue'

const { confirm } = useConfirm()
const kb = useKnowledgeStore()

const activeKbId = ref<number | null>(null)
const activeView = ref<'list' | 'details'>('list')
const activeKb = computed<KnowledgeBase | null>(() =>
  kb.knowledgeBases.find((k) => k.id === activeKbId.value) ?? null,
)

// 全局状态：上传进度追踪
const uploadingFiles = ref<{ name: string; progress: number; taskStatus: string; detailStatus: DocumentStatus | null; error?: string }[]>([])

// 弹窗状态
const showCreateModal = ref(false)
const showEditModal = ref(false)
const showUploadStrategyModal = ref(false)
const showChunksModal = ref(false)

// 临时流转状态
const pendingUploadFiles = ref<File[]>([])
const chunksDoc = ref<DocumentItem | null>(null)

onMounted(async () => {
  await kb.fetchKnowledgeBases()
  if (kb.knowledgeBases.length > 0) {
    await selectKb(kb.knowledgeBases[0].id)
    activeView.value = 'list'
  }
})

async function selectKb(id: number) {
  activeKbId.value = id
  activeView.value = 'details'
  await kb.fetchDocuments(id)
}

// ----- 知识库 CRUD -----
async function handleCreate(form: { name: string; description: string; chunk_strategy: string; enable_llm_clean: boolean }) {
  if (!form.name.trim()) {
    toast.error('请填写知识库名称')
    return
  }
  try {
    const created = await kb.createKnowledgeBase({ ...form, chunk_strategy: form.chunk_strategy as any })
    showCreateModal.value = false
    await selectKb(created.id)
    toast.success(`知识库“${created.name}”创建成功`)
  } catch (e: any) {
    toast.error(`创建失败: ${e?.message ?? '未知错误'}`)
  }
}

async function handleEditSave(form: { name: string; description: string }) {
  if (!activeKb.value || !form.name.trim()) return
  try {
    await kb.updateKnowledgeBase(activeKb.value.id, {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
    })
    showEditModal.value = false
    toast.success('保存成功')
  } catch (e: any) {
    toast.error(`更新失败: ${e?.message ?? '未知错误'}`)
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

// ----- 文档与上传管理 -----
function startUploadFlow(files: File[]) {
  pendingUploadFiles.value = files
  showUploadStrategyModal.value = true
}

async function confirmUpload(opts: { strategy?: 'recursive' | 'markdown' | 'semantic'; llmClean?: boolean }) {
  if (!activeKbId.value || pendingUploadFiles.value.length === 0) {
    showUploadStrategyModal.value = false
    return
  }
  const files = pendingUploadFiles.value
  showUploadStrategyModal.value = false
  pendingUploadFiles.value = []

  for (const file of files) {
    const trackItem = reactive<{ name: string; progress: number; taskStatus: string; detailStatus: DocumentStatus | null; error?: string }>({ name: file.name, progress: 0, taskStatus: 'pending', detailStatus: null })
    uploadingFiles.value.push(trackItem)
    try {
      await kb.uploadDocument(
        activeKbId.value,
        file,
        (task: TaskRecord) => {
          trackItem.progress = task.progress
          trackItem.taskStatus = task.status
          trackItem.detailStatus = task.detail_status || null
        },
        opts.strategy,
        opts.llmClean,
      )
    } catch (e: any) {
      trackItem.taskStatus = 'failed'
      trackItem.error = e?.message
    } finally {
      await kb.fetchDocuments(activeKbId.value)
      setTimeout(() => {
        if (trackItem.taskStatus === 'success' || trackItem.taskStatus === 'completed') {
          uploadingFiles.value = uploadingFiles.value.filter((f) => f !== trackItem)
        }
      }, 1500)
    }
  }
  await kb.fetchKnowledgeBases()
}

async function handleDeleteDoc(docId: number) {
  const doc = kb.documents.find((d) => d.id === docId)
  const ok = await confirm({
    title: '删除文档',
    message: `确定删除“${doc?.file_name ?? '该文档'}”吗？文档与其向量数据会一并删除。`,
    confirmText: '删除',
    variant: 'danger',
  })
  if (!ok || !activeKbId.value) return
  try {
    await kb.deleteDocument(activeKbId.value, docId)
    await kb.fetchKnowledgeBases()
    toast.success('文档已删除')
  } catch (e: any) {
    toast.error(`删除失败: ${e?.message ?? '未知错误'}`)
  }
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

// ----- 预览分块 -----
function openChunksPreview(doc: DocumentItem) {
  if (doc.status !== 'completed') {
    toast.error('该文档尚未处理完成，暂无分块可预览')
    return
  }
  chunksDoc.value = doc
  showChunksModal.value = true
}
</script>

<template>
  <div class="flex h-full bg-white dark:bg-zinc-950 font-sans text-zinc-900 dark:text-zinc-100">
    <!-- 侧边栏 -->
    <KbSidebar
      :knowledge-bases="kb.knowledgeBases"
      :loading="kb.loading"
      :active-kb-id="activeKbId"
      :active-view="activeView"
      @select="selectKb"
      @delete="handleDeleteKb"
      @create="showCreateModal = true"
    />

    <!-- 文档列表主区 -->
    <KbDocumentList
      :active-kb="activeKb"
      :documents="kb.documents"
      :uploading-files="uploadingFiles"
      @back="activeView = 'list'"
      @edit="showEditModal = true"
      @upload="startUploadFlow"
      @delete="handleDeleteDoc"
      @reprocess="handleReprocessDoc"
      @preview="openChunksPreview"
      :class="{'hidden md:flex': activeKbId === null || activeView === 'list'}"
    />

    <!-- 各类弹窗 -->
    <KbCreateModal
      v-if="showCreateModal"
      @close="showCreateModal = false"
      @create="handleCreate"
    />

    <KbEditModal
      v-if="showEditModal && activeKb"
      :initial-name="activeKb.name"
      :initial-description="activeKb.description || ''"
      @close="showEditModal = false"
      @save="handleEditSave"
    />

    <KbUploadStrategyModal
      v-if="showUploadStrategyModal"
      :files="pendingUploadFiles"
      @cancel="showUploadStrategyModal = false"
      @confirm="confirmUpload"
    />

    <KbChunksPreviewModal
      v-if="showChunksModal && chunksDoc && activeKbId"
      :kb-id="activeKbId"
      :document="chunksDoc"
      :fallback-strategy="activeKb?.chunk_strategy || ''"
      @close="showChunksModal = false; chunksDoc = null"
    />
  </div>
</template>
