/**
 * MCP 外部 Server 相关 API
 */
import request from './request'

export type MCPTransportType = 'stdio' | 'sse' | 'http'

export interface MCPServerConfig {
  id: number
  name: string
  description: string | null
  transport_type: MCPTransportType
  connection_uri: string
  env_vars: Record<string, string> | null
  is_active: boolean
  created_by: number
  created_at: string
  updated_at: string
  tool_count: number
  cached_tools: MCPToolInfo[] | null
}

export interface MCPToolInfo {
  name: string
  description: string
  inputSchema: Record<string, any>
}

export interface MCPServerConfigCreate {
  name: string
  description?: string
  transport_type: MCPTransportType
  connection_uri: string
  env_vars?: Record<string, string>
  cached_tools?: MCPToolInfo[]
  tool_count?: number
}

export function listMcpServers(): Promise<MCPServerConfig[]> {
  return request.get('/mcp/servers')
}

export function createMcpServer(payload: MCPServerConfigCreate): Promise<MCPServerConfig> {
  return request.post('/mcp/servers', payload)
}

export function deleteMcpServer(id: number): Promise<null> {
  return request.delete(`/mcp/servers/${id}`)
}

export function listMcpTools(id: number): Promise<MCPToolInfo[]> {
  return request.get(`/mcp/servers/${id}/tools`)
}

export function invokeMcpTool(
  id: number,
  toolName: string,
  args: Record<string, any> = {},
): Promise<{ tool_name: string; result: any }> {
  return request.post(`/mcp/servers/${id}/invoke`, {
    tool_name: toolName,
    arguments: args,
  })
}

// 测试连接（不入库），用于创建前先验证
export interface MCPConnectionTestRequest {
  transport_type: MCPTransportType
  connection_uri: string
  env_vars?: Record<string, string>
}

export interface MCPConnectionTestResult {
  ok: boolean
  tools_count: number
  latency_ms: number
  tools: string[]
  tools_detail: MCPToolInfo[]
  error: string | null
}

export function testMcpConnection(payload: MCPConnectionTestRequest): Promise<MCPConnectionTestResult> {
  return request.post('/mcp/servers/test', payload)
}

export function generateMcpDescription(payload: { server_name: string; tools: MCPToolInfo[] }): Promise<{ description: string }> {
  return request.post('/mcp/servers/generate-description', payload)
}

export function refreshMcpTools(id: number): Promise<MCPToolInfo[]> {
  return request.post(`/mcp/servers/${id}/refresh`)
}

export interface MCPServerConfigUpdate {
  name?: string
  description?: string
  is_active?: boolean
}

export function updateMcpServer(id: number, payload: MCPServerConfigUpdate): Promise<MCPServerConfig> {
  return request.patch(`/mcp/servers/${id}`, payload)
}
