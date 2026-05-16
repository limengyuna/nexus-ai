# 🐛 踩坑笔记（Troubleshooting）

> 项目开发过程中遇到的「值得记录」的工程问题、根因分析与修复方案。
> 既是给未来的自己排查参考，也是**面试时可以拿出来讲的工程沉淀**。

---

## 索引

| # | 问题 | 类别 | 难度 |
|---|------|------|:---:|
| [1](#1-fastapi-sse-streaming--depends-导致-sqlalchemy-not-persistent-错误) | FastAPI SSE Streaming + Depends 导致 SQLAlchemy `not persistent` 错误 | ⚙️ 框架机制 | ⭐⭐⭐ |
| [2](#2-windows-bat-脚本中文乱码--命令未识别) | Windows `.bat` 脚本中文乱码 / 命令未识别 | 🛠️ 工程踩坑 | ⭐⭐ |

---

## 1. FastAPI SSE Streaming + Depends 导致 SQLAlchemy `not persistent` 错误

> **日期**：2026-05-14
> **影响范围**：所有走 SSE 流式响应的接口（`POST /chat/sessions/{id}/messages/stream`）

### 🔴 现象

前端调用 SSE 接口，收到的事件流：

```text
event: status
data: {"step": "user_saved", "user_msg_id": 38}

event: error
data: {"message": "Instance '<ChatSession at 0x243457c4c80>' is not persistent within this Session", "type": "InvalidRequestError"}
```

第一个 `user_saved` 事件能正常发出（用户消息已落库），但紧接着的 `db.refresh(session)` 就报错——SQLAlchemy 抛 `InvalidRequestError: Instance is not persistent within this Session`。

### 🧠 根因分析

这是一个**典型的 FastAPI + SSE 生命周期不匹配问题**：

#### FastAPI 的 `Depends(get_db)` 生命周期

`get_db` 是一个生成器依赖：

```python
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()  # ← 路由函数 return 后立即执行
```

#### 普通 JSON 路由的执行流

```
[请求进入] → Depends(get_db) 开 session → 路由函数执行 → return JSON
                                                          ↓
                                               Depends finally 关 session
```

整个生命周期里 session 一直活着，没问题。

#### `StreamingResponse` 路由的执行流（坑！）

```
[请求进入] → Depends(get_db) 开 session → 路由函数执行 → return StreamingResponse 对象
                                                          ↓
                                              ❌ Depends finally **立刻**关 session
                                                          ↓
                                              ASGI 才开始消费 StreamingResponse
                                                          ↓
                                              generator 内的 ORM 对象已 detach
                                                          ↓
                                              访问 ORM 属性 → InvalidRequestError
```

**关键事实**：`return StreamingResponse(...)` 这一行**只是返回一个响应对象**，真正的流式数据生成发生在 ASGI 层后续消费 `event_generator()` 时——但 **FastAPI 不知道 generator 还要用 db**，它在路由函数 return 的瞬间就关掉了 db session。

这就是为什么第一次 `db.commit()` 能成功（commit 是同步的，发生在 generator 第一次被驱动前），而后续操作失败的原因。

### ✅ 修复方案

**核心思路**：generator 内部**不能依赖 `Depends` 注入的 db**，必须自己开一个独立的 session。

```python
async def stream_message(
    request: Request,
    session_id: int,
    payload: ChatRequest,
    db: Session = Depends(get_db),         # ← 这个 db 只用来做"路由层权限校验"
    current_user: User = Depends(get_current_user),
):
    # 1. 路由内同步校验（此时 db 还活着）
    session = ChatService.get_session(db, session_id)
    if session is None or session.user_id != current_user.id:
        raise HTTPException(404, "会话不存在")

    # 2. 提取需要传给 generator 的纯标量（避免传 ORM 对象进 generator）
    target_session_id = session.id
    target_user_id = current_user.id
    user_message = payload.message

    async def event_generator():
        # 3. ★ generator 内部开独立 session，独立于 FastAPI Depends 生命周期
        from app.core.database import SessionLocal
        local_db = SessionLocal()
        try:
            # 4. 用新 session 重新加载 ORM 对象
            local_session = ChatService.get_session(local_db, target_session_id)
            if local_session is None or local_session.user_id != target_user_id:
                yield f'event: error\ndata: {{"message": "会话不存在"}}\n\n'
                return

            async for ev_type, data in ChatService.chat_stream(local_db, local_session, user_message):
                yield f"event: {ev_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f'event: error\ndata: {json.dumps({"message": str(e)})}\n\n'
        finally:
            local_db.close()   # ★ generator 退出时自己关 session

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### 🎯 修复要点（4 条铁律）

1. **不要把 `Depends(get_db)` 的 db 传进 generator** —— generator 被驱动时 db 已死
2. **不要把 ORM 对象传进 generator** —— 即使你重开了 session，原 ORM 对象仍 detached
3. **`Depends` 的 db 只用来做路由层的快速校验**（权限、参数合法性等），失败立刻 raise
4. **从校验后的 ORM 提取纯标量**（id / user_id 等），传进 generator 重新查询

### 📖 相关文档

- FastAPI 官方相关讨论：[fastapi/fastapi#4719 - StreamingResponse + Depends 生命周期](https://github.com/fastapi/fastapi/discussions/4719)
- SQLAlchemy `InvalidRequestError: Instance is not persistent` 解释：当对象所属的 session 已被 close 或 expire，再访问其属性触发此错误

### 💬 面试讲点（高价值话术）

> "我做 SSE 流式对话接口时踩过一个**典型的 FastAPI 生命周期坑**：FastAPI 的 `Depends` 在路由函数 `return` 时就执行 finally 关 db，但 `StreamingResponse` 真正生成数据是在 ASGI 后续消费 generator 时。所以 generator 内部拿到的 db 已经关了，访问 ORM 对象会抛 `InvalidRequestError: not persistent`。
>
> 修复方案是 **'两段式 session 管理'**：
> - 路由层用 `Depends` 注入的 db 做**同步快速校验**（权限、参数）
> - 然后从 ORM 对象提取纯标量传给 generator
> - generator 内部用 `SessionLocal()` 开**独立 session**，重新加载 ORM 对象后再处理
>
> 这不仅是个 bug fix，更是对 FastAPI 异步生命周期的深入理解——很多教程都不会提这个坑。"

### 🔧 相关代码改动

| 文件 | 修改 |
|------|------|
| `backend/app/api/chat.py::stream_message` | 路由内做校验，generator 内开新 session |
| `backend/app/services/chat_service.py::chat_stream` | 接收外部传入的 db session（保持不变）|

---

## 2. Windows `.bat` 脚本中文乱码 / 命令未识别

> **日期**：2026-05-14
> **影响范围**：项目根目录 `nexus.bat` / `start.bat` / `stop.bat`

### 🔴 现象

双击 `nexus.bat`，菜单部分中文行被破坏：

```text
'[3]' is not recognized as an internal or external command
'��docker' is not recognized as an internal or external command
'开浏览器' is not recognized as an internal or external command
```

部分行能正常显示，部分行的中文被截断、当成命令执行。

### 🧠 根因分析

**不是简单的"UTF-8 不能用"，而是 CMD 在 `chcp 65001` 模式下有边界条件 bug**：

| 维度 | 关键事实 |
|------|---------|
| Windows CMD 默认编码 | GBK（中文系统，代码页 936）|
| `chcp 65001` | 切换到 UTF-8（代码页 65001）|
| GBK 中文 | 每字符 **2 字节** |
| UTF-8 中文 | 每字符 **3 字节** |

CMD 用 UTF-8 时，**特定中文字符的字节序列在某些位置会触发解析 bug**：

1. **行末字节巧合**：某些中文字符 UTF-8 末字节是 `\` (0x5C)，CMD 把它当转义符
2. **`echo` 缓冲区**：长行超过阈值时被截断
3. **全角符号紧贴 ASCII**：`echo [1] 启动模式（XXX）` 中 `（` 的字节序列让 CMD 把 `[1]` 当成命令

**对比**：同一目录另一个 `deploy.bat` 同样是 UTF-8 + `chcp 65001`，能正常运行——因为它**只用英文括号**、中文较少、行较短，**碰巧没触发** bug。

### ✅ 修复方案（最稳：转 GBK 编码）

**核心**：把 `.bat` 文件保存为 **GBK 编码**，去掉 `chcp 65001`，让 CMD 用原生编码解析。

#### 步骤 1：去掉 chcp 65001 行

```diff
  @echo off
- chcp 65001 >nul
  title NexusAI 控制台
```

#### 步骤 2：用 PowerShell 转码到 GBK

```powershell
$path = ".\nexus.bat"
$content = Get-Content -Path $path -Raw -Encoding UTF8
$gbk = [System.Text.Encoding]::GetEncoding("GBK")
[System.IO.File]::WriteAllText((Resolve-Path $path), $content, $gbk)
```

#### 步骤 3：防止 VS Code 把 bat 改回 UTF-8

在 `.vscode/settings.json` 配置 bat 文件强制用 GBK：

```json
{
  "[bat]": {
    "files.encoding": "gbk"
  }
}
```

### 🎯 三种方案对比

| 方案 | 适用 | 稳定性 |
|------|------|:------:|
| **A: GBK + 不要 chcp**（本项目采用）| 中文 Windows 11 主力开发 | ⭐⭐⭐⭐⭐ |
| B: UTF-8 + `chcp 65001` + 只用英文标点 | 跨平台编辑器友好 | ⭐⭐⭐ |
| C: UTF-8 with BOM + `chcp 65001` | Win 8.1+，兼顾两者 | ⭐⭐⭐⭐ |

### 💬 面试讲点

> "Windows bat 脚本的中文兼容性是个老问题。CMD 默认是 GBK 编码，每个中文字符 2 字节；UTF-8 是 3 字节。即使 `chcp 65001` 切到 UTF-8 模式，CMD 解析器对某些字节序列（比如末尾是 `0x5C` 的字符、长行、全角符号紧贴 ASCII）仍有 bug。
>
> 我的项目同目录另一个 bat 文件就**碰巧**能跑——因为它只用英文括号、中文少。我的菜单脚本用了全角括号 `（）` 就触发了 bug。最稳的方案是**保存为 CMD 原生的 GBK 编码**，配合 VS Code 的 `.vscode/settings.json` 锁定 bat 文件编码，避免误转。"

### 🔧 相关代码改动

| 文件 | 修改 |
|------|------|
| `nexus.bat` / `start.bat` / `stop.bat` | 转码 UTF-8 → GBK，删除 `chcp 65001` |
| `.vscode/settings.json` | 锁定 bat 文件编码为 GBK，防止误转 |

---

## 后续遇到的问题在此追加……

> 模板：复制下面这段开始新条目
>
> ```markdown
> ## N. 问题标题
>
> > **日期**：YYYY-MM-DD
> > **影响范围**：xxx
>
> ### 🔴 现象
> ### 🧠 根因分析
> ### ✅ 修复方案
> ### 🎯 修复要点
> ### 💬 面试讲点
> ```
