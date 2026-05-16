"""
业务逻辑层（Service Layer）

职责：
- 封装业务规则
- 编排 ORM 操作与外部服务调用
- 保持 API 路由层的薄

所有 Service 方法应接收 db (Session) 作为参数，便于事务管理与测试。
"""
