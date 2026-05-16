# NexusAI 前端

基于 Vue 3 + Vite + TypeScript + Pinia + TailwindCSS 的前端 SPA。

---

## 1. 技术栈

| 类别 | 选型 |
|------|------|
| 框架 | Vue 3.5 + Composition API |
| 构建工具 | Vite 5 |
| 类型系统 | TypeScript 5.6 |
| 状态管理 | Pinia 2 |
| 路由 | Vue Router 4 |
| HTTP 客户端 | Axios |
| 样式 | TailwindCSS 3 |

---

## 2. 启动

### 2.1 安装依赖

```powershell
# 在 frontend/ 目录下
npm install
```

> 推荐使用 Node.js 18+ 与 npm 9+。

### 2.2 启动开发服务器

```powershell
npm run dev
```

打开 http://localhost:5173 。

> 开发服务器已配置 Vite 代理，所有 `/api` 请求会自动转发到 `http://localhost:8000`。
> 务必先按照 `backend/README.md` 启动后端服务。

### 2.3 构建生产包

```powershell
npm run build
```

产物在 `dist/` 目录。

---

## 3. 目录结构

```text
frontend/
├── src/
│   ├── api/                # Axios 请求封装
│   │   ├── request.ts      # 统一拦截器、Token 注入
│   │   └── auth.ts         # 认证接口
│   ├── router/             # 路由配置（含全局守卫）
│   │   └── index.ts
│   ├── stores/             # Pinia 状态管理
│   │   └── auth.ts         # 认证状态（Token + 用户信息）
│   ├── views/              # 页面视图
│   │   ├── LoginView.vue   # 登录/注册（双 Tab）
│   │   └── HomeView.vue    # 首页（占位）
│   ├── App.vue             # 根组件（路由出口）
│   ├── main.ts             # 应用入口
│   └── style.css           # TailwindCSS 入口
├── index.html              # HTML 模板
├── package.json
├── tailwind.config.js      # TailwindCSS 配置
├── postcss.config.js
├── tsconfig.json           # 项目引用入口
├── tsconfig.app.json       # 应用代码 TS 配置
├── tsconfig.node.json      # 构建脚本 TS 配置
└── vite.config.ts          # Vite 配置（含代理）
```

---

## 4. 验证流程

1. 启动后端服务（参考 `backend/README.md`）
2. 启动前端 `npm run dev`
3. 访问 http://localhost:5173 → 自动跳转 `/login`
4. 切换到"注册"Tab → 填写用户名密码 → 提交
5. 注册成功后自动登录，跳转到首页 `/`
6. 首页右上角可看到用户名和角色，点击"登出"返回登录页

---

## 5. 阶段一已实现

- [x] 项目骨架与构建工具链
- [x] TailwindCSS + 主题色配置
- [x] Pinia + Vue Router 集成
- [x] Axios 统一封装（Token 注入 + 拦截器 + 401 自动跳转）
- [x] 认证 Store（登录 / 登出 / 当前用户 / 持久化）
- [x] 登录注册页（双模式切换）
- [x] 首页（路由守卫保护）

阶段四将补充：对话界面、知识库管理、MCP 配置等。
