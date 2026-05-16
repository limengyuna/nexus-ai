/**
 * Skills 相关 API（只读）
 */
import request from './request'

export interface SkillInfo {
  name: string
  description: string
  required_tools: string[]
  trigger_keywords: string[]
}

export interface SkillTestResult {
  skill_name: string
  answer: string
  tool_calls: any[]
  meta: Record<string, any>
}

export function listSkills(): Promise<SkillInfo[]> {
  return request.get('/skills')
}

export function testSkill(name: string, userInput: string, kbId?: number | null): Promise<SkillTestResult> {
  return request.post(`/skills/${name}/test`, {
    user_input: userInput,
    ...(kbId !== undefined && kbId !== null ? { kb_id: kbId } : {}),
  })
}
