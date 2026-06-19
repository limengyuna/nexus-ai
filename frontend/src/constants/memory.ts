// src/constants/memory.ts

// 预置的系统白名单槽位定义
export const defaultSlots = [
  { key: 'profile.role', name: '用户角色', type: 'profile', desc: '用户在组织或工作中的角色定位', valType: 'string' },
  { key: 'profile.primary_language', name: '偏好交流语言', type: 'profile', desc: '用户与 AI 沟通时偏好的主要语言', valType: 'string' },
  { key: 'agent.response_style', name: '回答风格偏好', type: 'agent', desc: '系统回答的文风与排版特点', valType: 'enum', options: ['concise', 'detailed', 'step_by_step', 'formal'] },
  { key: 'agent.detail_level', name: '回答详细程度', type: 'agent', desc: 'AI 生成内容的展开和详细程度', valType: 'enum', options: ['low', 'medium', 'high'] },
  { key: 'agent.clarification_preference', name: '信息澄清偏好', type: 'agent', desc: '当用户意图含糊时，AI 偏向直接假设还是先提问', valType: 'enum', options: ['ask_first', 'assume_and_explain'] },
  { key: 'knowledge.preferred_citation_style', name: '引用呈现风格', type: 'knowledge', desc: '知识库 RAG 检索回答时的文献标注样式', valType: 'string' },
  { key: 'output.default_format', name: '默认输出格式', type: 'output', desc: 'AI 吐出回答的默认结构化格式', valType: 'enum', options: ['paragraph', 'list', 'table', 'markdown', 'json'] },
  { key: 'domain.business_domain', name: '聚焦业务领域', type: 'domain', desc: '用户长期关注或从事的特定垂直领域', valType: 'string' },
  { key: 'constraint.must_follow', name: '必须遵守的硬性规则', type: 'constraint', desc: '在任何会话中大模型均绝对不可违反的规则', valType: 'string' },
  { key: 'constraint.do_not_do', name: '严禁越界行为', type: 'constraint', desc: '用户明确禁止 AI 做出的行为、语气或操作', valType: 'string' },
  { key: 'constraint.data_sensitivity', name: '敏感数据处理偏好', type: 'constraint', desc: '对于敏感、保密或个人隐私信息的合规处理逻辑', valType: 'string' }
]
