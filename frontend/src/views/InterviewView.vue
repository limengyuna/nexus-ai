<script setup lang="ts">
/**
 * 面试 QA 文档预览 + 导出页面（隐藏入口）
 *
 * 功能：从后端获取最新 md 内容，渲染为手机友好的 HTML 预览，支持一键导出 HTML 文件
 */
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { Download, ArrowLeft, Loader2 } from 'lucide-vue-next'
import MarkdownIt from 'markdown-it'
import request from '@/api/request'

const router = useRouter()
const loading = ref(true)
const mdContent = ref('')
const error = ref('')

// markdown-it 实例
const md = new MarkdownIt({
  html: true,
  breaks: true,
  linkify: true,
})

// 渲染后的 HTML
const renderedHtml = computed(() => {
  if (!mdContent.value) return ''
  return md.render(mdContent.value)
})

// 获取 md 内容
async function fetchContent() {
  loading.value = true
  error.value = ''
  try {
    const res: any = await request.get('/internal/interview-qa')
    mdContent.value = res.content
  } catch (e: any) {
    error.value = e.message || '获取文档失败'
  } finally {
    loading.value = false
  }
}

// 导出为独立 HTML 文件（样式内联，手机友好）
function exportHtml() {
  const htmlDoc = buildExportHtml(renderedHtml.value)
  const blob = new Blob([htmlDoc], { type: 'text/html;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `面试QA_${new Date().toISOString().slice(0, 10)}.html`
  a.click()
  URL.revokeObjectURL(url)
}

// 构建导出的完整 HTML（内联样式，手机浏览器直接打开即可）
function buildExportHtml(content: string): string {
  return `<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>面试 QA 复盘</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
  line-height: 1.8;
  color: #1a1a1a;
  background: #f8f9fa;
  padding: 16px;
  max-width: 100%;
}
h1 { font-size: 1.5rem; margin: 24px 0 12px; color: #1a1a1a; border-bottom: 2px solid #6366f1; padding-bottom: 8px; }
h2 { font-size: 1.25rem; margin: 20px 0 10px; color: #4f46e5; }
h3 { font-size: 1.1rem; margin: 16px 0 8px; color: #1e293b; }
p { margin: 8px 0; }
blockquote {
  border-left: 4px solid #6366f1;
  background: #eef2ff;
  padding: 12px 16px;
  margin: 12px 0;
  border-radius: 0 8px 8px 0;
  font-size: 0.95rem;
}
code {
  background: #e2e8f0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.85em;
  font-family: 'Fira Code', 'JetBrains Mono', monospace;
}
pre {
  background: #1e293b;
  color: #e2e8f0;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 12px 0;
  font-size: 0.85rem;
}
pre code { background: none; padding: 0; color: inherit; }
ul, ol { padding-left: 20px; margin: 8px 0; }
li { margin: 4px 0; }
strong { color: #1e40af; }
hr { border: none; border-top: 1px solid #e2e8f0; margin: 24px 0; }
table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 0.9rem; }
th, td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
th { background: #f1f5f9; font-weight: 600; }
em { color: #dc2626; font-style: normal; }
</style>
</head>
<body>
${content}
</body>
</html>`
}

onMounted(fetchContent)
</script>

<template>
  <div class="h-full flex flex-col bg-gray-50 dark:bg-gray-950">
    <!-- 顶部工具栏 -->
    <header class="flex items-center justify-between px-6 py-3 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 flex-shrink-0">
      <div class="flex items-center gap-3">
        <button
          class="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 dark:text-gray-400"
          @click="router.back()"
        >
          <ArrowLeft :size="20" />
        </button>
        <h1 class="text-lg font-semibold text-gray-800 dark:text-gray-100">面试 QA 复盘</h1>
      </div>
      <button
        class="flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
        :disabled="loading || !!error"
        @click="exportHtml"
      >
        <Download :size="16" />
        导出 HTML
      </button>
    </header>

    <!-- 内容区 -->
    <div class="flex-1 overflow-y-auto p-6">
      <!-- 加载中 -->
      <div v-if="loading" class="flex items-center justify-center h-64">
        <Loader2 :size="32" class="animate-spin text-primary-500" />
      </div>

      <!-- 错误 -->
      <div v-else-if="error" class="text-center py-16">
        <p class="text-red-500 text-lg">{{ error }}</p>
        <button class="mt-4 px-4 py-2 bg-primary-600 text-white rounded-lg" @click="fetchContent">重试</button>
      </div>

      <!-- 预览 -->
      <article
        v-else
        class="prose prose-sm dark:prose-invert max-w-4xl mx-auto bg-white dark:bg-gray-900 rounded-xl shadow-sm p-8"
        v-html="renderedHtml"
      />
    </div>
  </div>
</template>
