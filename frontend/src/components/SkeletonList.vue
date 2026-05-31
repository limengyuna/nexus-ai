<script setup lang="ts">
/**
 * 骨架屏列表 —— 渲染 N 行 Skeleton 占位
 *
 * 用于：会话列表 / 知识库列表 / MCP 列表 初次加载
 */
import Skeleton from './Skeleton.vue'

const props = withDefaults(
  defineProps<{
    rows?: number              // 行数，默认 5
    itemClass?: string         // 单行样式（高度等）
    gap?: string               // 行间距 Tailwind 类，默认 space-y-2
  }>(),
  {
    rows: 5,
    itemClass: 'h-10 w-full',
    gap: 'space-y-2',
  },
)
</script>

<template>
  <div :class="gap">
    <Skeleton
      v-for="i in props.rows"
      :key="i"
      :class="props.itemClass"
    />
  </div>
</template>
