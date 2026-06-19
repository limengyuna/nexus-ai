<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import { Pencil, Plus, Search, Trash2, X } from 'lucide-vue-next'
import SkeletonList from '@/components/SkeletonList.vue'
import type { ChatSession } from '@/api/chat'

const props = defineProps<{
  sessions: ChatSession[]
  activeSessionId: number | null
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'select', id: number): void
  (e: 'delete', id: number): void
  (e: 'create'): void
  (e: 'rename', id: number, newTitle: string): void
}>()

const searchKeyword = ref('')
const renamingSessionId = ref<number | null>(null)
const renameInput = ref('')

const filteredSessions = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return props.sessions
  return props.sessions.filter((s) => s.title.toLowerCase().includes(kw))
})

// 按时间分组逻辑
function parseUtcDate(dateStr: string) {
  if (!dateStr) return new Date()
  if (!dateStr.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(dateStr)) {
    return new Date(dateStr + 'Z')
  }
  return new Date(dateStr)
}

function isSameDay(d1: Date, d2: Date) {
  return d1.getFullYear() === d2.getFullYear() &&
         d1.getMonth() === d2.getMonth() &&
         d1.getDate() === d2.getDate()
}

function isYesterday(d1: Date, d2: Date) {
  const yesterday = new Date(d2)
  yesterday.setDate(yesterday.getDate() - 1)
  return isSameDay(d1, yesterday)
}

function formatSessionTime(dateStr: string) {
  if (!dateStr) return ''
  const d = parseUtcDate(dateStr)
  const now = new Date()
  if (isSameDay(d, now)) {
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  if (isYesterday(d, now)) {
    return '昨天'
  }
  return `${d.getMonth() + 1}-${d.getDate()}`
}

const groupedSessions = computed(() => {
  const today: any[] = []
  const yesterday: any[] = []
  const earlier: any[] = []
  const now = new Date()

  const sortedSessions = [...filteredSessions.value].sort((a, b) => {
    const timeA = parseUtcDate(a.updated_at || a.created_at).getTime()
    const timeB = parseUtcDate(b.updated_at || b.created_at).getTime()
    return timeB - timeA
  })

  sortedSessions.forEach(s => {
    const d = parseUtcDate(s.updated_at || s.created_at)
    if (isSameDay(d, now)) {
      today.push(s)
    } else if (isYesterday(d, now)) {
      yesterday.push(s)
    } else {
      earlier.push(s)
    }
  })

  const groups = []
  if (today.length > 0) groups.push({ label: '今天', sessions: today })
  if (yesterday.length > 0) groups.push({ label: '昨天', sessions: yesterday })
  if (earlier.length > 0) groups.push({ label: '更早', sessions: earlier })
  return groups
})

function handleSelect(sessionId: number) {
  if (renamingSessionId.value !== null && renamingSessionId.value !== sessionId) {
    cancelRename()
  }
  emit('select', sessionId)
}

function startRename(sessionId: number, currentTitle: string) {
  renamingSessionId.value = sessionId
  renameInput.value = currentTitle
  nextTick(() => {
    const inputEl = document.querySelector<HTMLInputElement>(`[data-rename-input="${sessionId}"]`)
    if (inputEl) {
      inputEl.focus()
      inputEl.select()
    }
  })
}

function saveRename() {
  if (renamingSessionId.value === null) return
  const newTitle = renameInput.value.trim()
  const sid = renamingSessionId.value
  renamingSessionId.value = null
  if (newTitle) {
    emit('rename', sid, newTitle)
  }
}

function cancelRename() {
  renamingSessionId.value = null
  renameInput.value = ''
}
</script>

<template>
  <div class="w-64 fixed md:relative inset-y-0 left-0 z-50 bg-white dark:bg-[#09090b] border-r border-gray-100 dark:border-gray-800/40 flex flex-col flex-shrink-0 shadow-2xl md:shadow-none overflow-hidden">
    <div class="pt-5 pb-3 px-3 space-y-4">
      <!-- 新建对话按钮 -->
      <div class="px-1">
        <button
          class="w-full py-2.5 px-3 bg-[#1e2333] hover:bg-[#262c3f] dark:bg-zinc-100 dark:hover:bg-zinc-200 text-white dark:text-zinc-900 text-xs font-semibold rounded-[12px] transition-all duration-200 flex items-center justify-center gap-1.5 shadow-sm active:scale-[0.98]"
          title="快捷键: Ctrl+K"
          @click="$emit('create')"
        >
          <Plus :size="15" :stroke-width="2.5" class="opacity-90" />
          <span>新建对话</span>
          <kbd class="hidden lg:inline-block ml-1.5 px-1.5 py-0.5 text-[9px] font-mono bg-white/10 dark:bg-black/10 text-white/80 dark:text-zinc-600 rounded">⌘K</kbd>
        </button>
      </div>

      <!-- 会话搜索 -->
      <div class="relative px-1">
        <Search :size="13" class="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" />
        <input
          v-model="searchKeyword"
          type="text"
          placeholder="搜索会话..."
          class="w-full pl-9 pr-7 py-2 text-xs bg-gray-50 dark:bg-zinc-900/40 text-gray-700 dark:text-gray-200 rounded-[10px] border border-transparent focus:bg-white dark:focus:bg-zinc-900 focus:border-gray-200 dark:focus:border-zinc-700 focus:outline-none focus:ring-4 focus:ring-black/5 dark:focus:ring-white/5 transition-all duration-200 placeholder:text-gray-400"
        />
        <button
          v-if="searchKeyword"
          class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
          @click="searchKeyword = ''"
        >
          <X :size="12" />
        </button>
      </div>
    </div>

    <!-- 列表滚动区 -->
    <div class="flex-1 overflow-y-auto px-2 py-2 space-y-1">
      <SkeletonList
        v-if="loading && sessions.length === 0"
        :rows="5"
        item-class="h-9 w-full rounded-sm"
        class="px-1"
      />
      <div v-else-if="sessions.length === 0" class="text-center text-xs text-gray-400/80 py-10 font-medium">
        暂无对话<br>点击上方按钮创建
      </div>
      <div v-else-if="filteredSessions.length === 0" class="text-center text-xs text-gray-400/80 py-10 font-medium">
        没有匹配的会话
      </div>

      <template v-for="group in groupedSessions" :key="group.label">
        <div class="text-[11px] font-bold text-gray-400 dark:text-gray-500 mt-5 mb-2 px-3 tracking-wider">{{ group.label }}</div>
        <div
          v-for="s in group.sessions"
          :key="s.id"
          class="group flex items-center justify-between gap-1.5 px-3 py-2.5 mx-1.5 rounded-[10px] cursor-pointer text-xs transition-all duration-200 relative overflow-hidden"
          :class="activeSessionId === s.id
            ? 'bg-blue-50/60 dark:bg-blue-900/15 ring-1 ring-blue-500/15 dark:ring-blue-400/20 text-slate-800 dark:text-slate-100 shadow-sm font-semibold'
            : 'text-slate-600 dark:text-slate-400 font-medium hover:bg-slate-50 dark:hover:bg-zinc-900/50 hover:text-slate-800 dark:hover:text-slate-200'"
          @click="handleSelect(s.id)"
          @dblclick="startRename(s.id, s.title)"
        >
          <!-- 重命名 -->
          <input
            v-if="renamingSessionId === s.id"
            v-model="renameInput"
            :data-rename-input="s.id"
            type="text"
            class="flex-1 px-2 py-0.5 text-xs bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-100 border border-zinc-400 dark:border-zinc-600 rounded-sm outline-none ring-4 ring-primary-500/10"
            @click.stop
            @keydown.enter.prevent="saveRename"
            @keydown.esc.prevent="cancelRename"
            @blur="saveRename"
          />
          <!-- 普通显示 -->
          <template v-else>
            <span class="truncate flex-1 pr-6" :title="s.title">{{ s.title }}</span>
            <span class="text-[10px] text-gray-400/80 dark:text-gray-500 whitespace-nowrap transition-opacity duration-200 group-hover:opacity-0 group-hover:pointer-events-none">
              {{ formatSessionTime(s.updated_at || s.created_at) }}
            </span>
            <div class="absolute right-0 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity bg-gradient-to-l from-slate-50 via-slate-50 to-transparent dark:from-zinc-900 dark:via-zinc-900 pl-6 pr-2 py-2">
              <button
                class="p-1 text-gray-400 hover:text-zinc-900 dark:text-zinc-100 dark:hover:text-primary-400 transition-colors"
                title="重命名（双击也可）"
                @click.stop="startRename(s.id, s.title)"
              >
                <Pencil :size="12" />
              </button>
              <button
                class="p-1 text-gray-400 hover:text-red-500 transition-colors"
                title="删除会话"
                @click.stop="$emit('delete', s.id)"
              >
                <Trash2 :size="12" />
              </button>
            </div>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>
