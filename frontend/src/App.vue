<script setup lang="ts">
// 根组件：承载路由出口 + 全局 Toast 通知 + 全局确认弹窗
import { RouterView } from 'vue-router'
import { Toaster } from 'vue-sonner'

import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { useTheme } from '@/composables/useTheme'

const { theme } = useTheme()
</script>

<template>
  <RouterView />
  <!-- 全局 Toast 容器（右上角，默认 3s 自动消失，跟随当前主题）-->
  <Toaster :theme="theme" position="top-right" :duration="3000" rich-colors close-button />
  <!-- 全局自定义确认弹窗（替代浏览器 confirm） -->
  <ConfirmDialog />
</template>
