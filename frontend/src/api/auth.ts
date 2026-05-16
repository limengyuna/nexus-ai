/**
 * 认证相关 API 封装
 *
 * 与后端 /api/v1/auth/* 接口对齐。
 */
import request from './request'

// ---------- 类型定义（与后端 Schemas 对齐） ----------
export interface UserInfo {
  id: number
  username: string
  role: 'admin' | 'user'
  is_active: boolean
  created_at: string
}

export interface TokenData {
  access_token: string
  token_type: string
  expires_in: number
}

// ---------- API 方法 ----------

/**
 * 用户注册
 */
export function register(username: string, password: string): Promise<UserInfo> {
  return request.post('/auth/register', { username, password })
}

/**
 * 用户登录（使用 OAuth2 表单格式提交）
 */
export function login(username: string, password: string): Promise<TokenData> {
  // 后端使用 OAuth2PasswordRequestForm，必须用 form-urlencoded 提交
  const formData = new URLSearchParams()
  formData.append('username', username)
  formData.append('password', password)
  return request.post('/auth/login', formData, {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  })
}

/**
 * 获取当前登录用户信息
 */
export function getMe(): Promise<UserInfo> {
  return request.get('/auth/me')
}
