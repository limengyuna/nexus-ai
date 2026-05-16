/**
 * Axios 请求封装
 *
 * 职责：
 * 1. 统一基础 URL（开发环境通过 Vite 代理到后端 8000）
 * 2. 自动注入 JWT 令牌到请求头
 * 3. 拦截响应，统一处理后端的 ApiResponse 格式
 * 4. 401 自动登出 + 跳转登录页
 */
import axios from 'axios'
import type { AxiosInstance, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

// 后端统一响应格式（与后端 ApiResponse 对齐）
export interface ApiResponse<T = unknown> {
  code: number
  message: string
  data: T | null
}

// ---------- 创建 Axios 实例 ----------
const request: AxiosInstance = axios.create({
  baseURL: '/api/v1',  // 开发环境由 Vite 代理转发到 http://localhost:8000
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ---------- 请求拦截器：注入 Token ----------
request.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

// ---------- 响应拦截器：统一错误处理 ----------
request.interceptors.response.use(
  // 成功：解包 ApiResponse.data 直接返回业务数据
  (response: AxiosResponse<ApiResponse>) => {
    const { code, message, data } = response.data
    if (code === 0) {
      return data as any
    }
    // 业务错误码非 0
    return Promise.reject(new Error(message || '业务错误'))
  },
  // 失败：处理 HTTP 错误
  (error) => {
    const status = error.response?.status
    const message = error.response?.data?.message || error.message || '网络错误'

    if (status === 401) {
      // 令牌失效或未登录，清除本地状态并跳转登录页
      localStorage.removeItem('access_token')
      // 避免循环跳转：如已在登录页则不再跳转
      if (!window.location.pathname.startsWith('/login')) {
        window.location.href = '/login'
      }
    }

    return Promise.reject(new Error(message))
  },
)

export default request
