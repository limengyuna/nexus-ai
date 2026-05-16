/**
 * Markdown 渲染工具
 *
 * 用 markdown-it + highlight.js 把 Agent 回复的 Markdown 文本转为带语法高亮的 HTML。
 */
import hljs from 'highlight.js'
import MarkdownIt from 'markdown-it'

import 'highlight.js/styles/github.css'

// 提前获取 escapeHtml，避免 highlight 回调中 md 自引用导致隐式 any
const { escapeHtml } = MarkdownIt().utils

const md: MarkdownIt = new MarkdownIt({
  html: false,       // 不允许直接 HTML，防 XSS
  breaks: true,      // 换行符转 <br>
  linkify: true,     // 自动识别 URL
  typographer: true, // 智能引号等排版优化
  highlight: (code: string, lang: string): string => {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="hljs"><code>${hljs.highlight(code, { language: lang, ignoreIllegals: true }).value}</code></pre>`
      } catch {
        // ignore，走默认渲染
      }
    }
    return `<pre class="hljs"><code>${escapeHtml(code)}</code></pre>`
  },
})

// 让链接默认在新标签打开
const defaultLinkRender = md.renderer.rules.link_open
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const aIndex = tokens[idx].attrIndex('target')
  if (aIndex < 0) {
    tokens[idx].attrPush(['target', '_blank'])
    tokens[idx].attrPush(['rel', 'noopener noreferrer'])
  }
  if (defaultLinkRender) {
    return defaultLinkRender(tokens, idx, options, env, self)
  }
  return self.renderToken(tokens, idx, options)
}

export function renderMarkdown(text: string): string {
  return md.render(text || '')
}
