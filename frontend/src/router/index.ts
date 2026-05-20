/**
 * Vue Router 配置
 *
 * 路由守卫：未登录用户访问受保护页面时跳转到 /login
 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import { useAuthStore } from '@/stores/auth'

// 应用名称常量（document.title 后缀）
const APP_NAME = 'NexusAI'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/views/LoginView.vue'),
    meta: { requiresAuth: false, title: '登录' },
  },
  {
    path: '/',
    component: () => import('@/layouts/AppLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/chat' },
      {
        path: 'chat',
        name: 'chat',
        component: () => import('@/views/ChatView.vue'),
        meta: { title: '智能对话' },
      },
      {
        path: 'knowledge',
        name: 'knowledge',
        component: () => import('@/views/KnowledgeView.vue'),
        meta: { title: '知识库' },
      },
      {
        path: 'skills',
        name: 'skills',
        component: () => import('@/views/SkillsView.vue'),
        meta: { title: 'Skills' },
      },
      {
        path: 'mcp',
        name: 'mcp',
        component: () => import('@/views/MCPView.vue'),
        meta: { title: 'MCP 配置' },
      },
      {
        path: 'memory',
        name: 'memory',
        component: () => import('@/views/MemoryView.vue'),
        meta: { title: '长期记忆' },
      },
    ],
  },
  // 404 页面：放在最后，匹配所有未命中的路径
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/views/NotFoundView.vue'),
    meta: { requiresAuth: false, title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ---------- 全局前置守卫：未登录拦截 ----------
router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    // 携带原目标 URL，登录成功后回跳
    return { name: 'login', query: { redirect: to.fullPath } }
  }
})

// ---------- 全局后置钩子：动态设置浏览器标签页标题 ----------
router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · ${APP_NAME}` : APP_NAME
})

export default router
