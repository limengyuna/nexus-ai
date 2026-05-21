/**
 * 认证状态管理 (Pinia Store)
 *
 * 管理：当前用户信息、JWT 令牌、登录/登出动作。
 * 令牌持久化到 localStorage，刷新页面不丢失登录态。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { getMe, login as loginApi } from '@/api/auth'
import type { UserInfo } from '@/api/auth'

const TOKEN_KEY = 'access_token'

export const useAuthStore = defineStore('auth', () => {
  // ---------- 状态 ----------
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const userInfo = ref<UserInfo | null>(null)

  // ---------- 计算属性 ----------
  const isAuthenticated = computed(() => !!token.value)

  // ---------- Action: 登录 ----------
  async function login(username: string, password: string) {
    const data = await loginApi(username, password)
    token.value = data.access_token
    localStorage.setItem(TOKEN_KEY, data.access_token)
    // 登录成功后立即拉取用户信息
    await fetchUserInfo()
  }

  // ---------- Action: 获取当前用户信息 ----------
  async function fetchUserInfo() {
    const info = await getMe()
    userInfo.value = info
    return info
  }

  // ---------- Action: 登出 ----------
  function logout() {
    token.value = ''
    userInfo.value = null
    localStorage.removeItem(TOKEN_KEY)
    // 清除聊天相关的本地缓存，防止切换用户后看到上一个用户的数据
    localStorage.removeItem('nexus_thinking_traces')
  }

  return {
    // state
    token,
    userInfo,
    // getter
    isAuthenticated,
    // actions
    login,
    fetchUserInfo,
    logout,
  }
})
