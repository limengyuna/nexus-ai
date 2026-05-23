"""
LLM 文档结构修订器（标注式，可选预处理层）

设计哲学：
  - LLM 只做"标注"，不做"重写"
  - 原文文字一个字都不会被 LLM 篡改
  - 代码按 LLM 给出的行号决定加 / 去 # 前缀

工作流程：
  1. 输入：启发式解析后的 Markdown 文本（已含部分 #/##/###）
  2. 按行切段（每段 ~80 行），逐段问 LLM
  3. LLM 返回 JSON：
       - add: 应升级为标题但当前没 # 的行（含 level）
       - remove: 当前被错标为标题的行
  4. 代码按 JSON 应用修订（仅在行首增减 # 前缀，不动文字）
  5. 任何阶段失败（JSON 不合法 / 数量异常 / 行号越界）整段回退原文

防线（共 6 道）：
  - 防线 1：Prompt 严格约束 + few-shot 示例
  - 防线 2：JSON 解析必须合法（否则段回退）
  - 防线 3：数量护栏（add ≤ 5% 行数，remove ≤ 当前标题数 × 80%）
  - 防线 4：行号越界过滤（不在段范围内的项静默丢弃）
  - 防线 5：内容不可变（应用时 LLM 没法改文字）
  - 防线 6：异常兜底（任何异常 → 段回退原文）

相比"重写式"的优势：
  - 内容篡改风险降到 0（代码控制 # 前缀，LLM 摸不到原文）
  - Token 消耗降低 ~60%（输出 JSON 而非整段重写）
  - 校验简单（JSON 格式 + 数量范围）
  - 速度提升明显
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from loguru import logger

from app.agent.llm import get_llm_fast


# ---------- 配置常量 ----------

# 单段处理行数。短一点更稳：输入小、输出小、出错隔离更细
_SEGMENT_LINES = 80

# add 数量护栏：单段 LLM 标记的"新增标题"不能超过段行数的 5%
# 否则视为 LLM 失控（把正文也标成了标题）
_ADD_RATIO_LIMIT = 0.05

# remove 数量护栏：单段移除的"已有标题"占比不能超过 50%
# 启发式版的标题大概率是对的，LLM 修订应该是少量纠错而非大量推翻
_REMOVE_RATIO_LIMIT = 0.50

# 行号正则：从每行展示文本中提取（用于校验 LLM 引用的行号是否合法）
_LINE_PREFIX_RE = re.compile(r"^L(\d{4,5}):\s")

# 现有 Markdown 标题前缀（仅匹配行首 1~6 个 # 后跟空格）
_HEADING_PREFIX_RE = re.compile(r"^(#{1,6})\s")


# ---------- Prompt 设计（防线 1：指令级约束） ----------

_ANNOTATOR_SYSTEM_PROMPT = """\
你是文档结构标注员。你的任务非常严格：只返回一个 JSON 对象，告诉我哪些行应该是标题，哪些行被错误地标为了标题。

【核心原则 - 极度重要】：
**保守优先**。如果某行已经有 # 前缀，倾向于保留它（不要 remove），除非该行明显是正文（如完整句子、长段落开头）。
不确定时，宁可漏标也不要乱标，宁可保留也不要乱删。

【绝对禁止】：
- 输出任何文字解释、前后缀、Markdown 代码块包装
- 修改原文内容（你只能"指出哪一行"，不能"改写哪一行"）
- 把"第X条"这种法律条款标为标题（数量太多会导致文档过度切碎）
- 把以句号、问号、感叹号结尾的完整句子标为标题
- 把超过 30 个字的长句标为标题
- 删除已有 # 前缀的常见无编号标题词（见下方白名单）

【真标题判断规则】：
A. 含层级编号的（按优先级）：
   1. 第X编 / 第X章 / 第X部分 → level 1
   2. 第X节 / 数字层级 X.Y → level 2
   3. 数字层级 X.Y.Z 及更深 → level 3

B. 无编号但属于常见标题词（同样视为真标题，倾向 level 1 或 2，不要 remove）：
   摘要、Abstract、前言、引言、绪论、目录、致谢、参考文献、附录、
   声明、独创性声明、使用授权声明、原创性声明、签名、作者签名、导师签名、
   结论、总结、展望、未来工作

C. 不应是标题：
   - 法律条款"第X条" / "第三百九十四条" 等
   - 完整句子（含句号、问号、感叹号结尾）
   - 长句（> 30 字）
   - 列举项（"（一）"、"（二）"、"1."等列表项）

【输入格式】：
每行带行号前缀 L0001、L0002 等。已经有 # 前缀的行表示当前已被识别为标题。

【输出格式】（严格 JSON，且仅 JSON）：
{"add": [{"line": 行号, "level": 1或2或3}, ...], "remove": [行号, ...]}

- add: 应升级为标题但当前没 # 前缀的行
- remove: 当前有 # 前缀但其实是正文（极保守使用，遇到白名单词绝不 remove）

如果无需修改，返回：{"add": [], "remove": []}

【正面示例 1】：法律文档误标
输入：
L0001: 第十七章 抵押权
L0002: 第一节 一般抵押权
L0003: # 第三百九十四条 为担保债务的履行，债务人或者第三人...
L0004: 前款规定的债务人或者第三人为抵押人。
输出：
{"add": [{"line": 1, "level": 1}, {"line": 2, "level": 2}], "remove": [3]}
理由：第十七章/第一节是真标题需补 #；第三百九十四条是法律条款不是标题需移除。

【正面示例 2】：学术文档无编号标题（注意 - 不要 remove）
输入：
L0010: ## 毕业论文（设计）使用授权声明
L0011: 本人完全了解成都工业学院有关保留、使用论文的规定...
L0020: ## 摘 要
L0021: 随着"搭子社交"在年轻人中迅速兴起...
L0050: ### 3.1.2 经济可行性分析
L0051: 本系统开发过程使用的技术栈都是开源免费的方案...
输出：
{"add": [], "remove": []}
理由：使用授权声明、摘要都是无编号常见标题词，启发式已正确识别，绝对不要 remove。3.1.2 也已正确识别。
"""


_ANNOTATOR_USER_PROMPT_TEMPLATE = """\
请按 system 规则标注以下文档片段，只返回 JSON：

{display}
"""


# ---------- 数据结构 ----------

@dataclass
class _AnnotationResult:
    """LLM 标注结果（已校验过的，可直接应用）"""
    add: List[Tuple[int, int]]      # [(line_no, level), ...] 绝对行号
    remove: List[int]                # [line_no, ...] 绝对行号


# ---------- 工具函数 ----------

def _build_display_lines(lines: List[str], offset: int) -> str:
    """
    把行列表组装成带行号的展示文本（喂给 LLM）

    :param lines: 原始行（含已有的 # 前缀）
    :param offset: 第一行的"绝对行号"（从 1 起算，让 LLM 直接用绝对行号回答）
    :return: 形如 "L0001: ...\nL0002: ..." 的多行字符串
    """
    return "\n".join(f"L{offset + i:04d}: {line}" for i, line in enumerate(lines))


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """
    解析 LLM 返回的 JSON。容错处理：
      - LLM 偶尔会把 JSON 包在 ```json ... ``` 里
      - LLM 偶尔会输出额外的解释文字

    解析失败抛异常（由调用方降级处理）
    """
    text = raw.strip()
    # 剥离可能的 markdown 代码块包装
    if text.startswith("```"):
        # 移除首尾的 ``` 行
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    # 取第一个 { 到最后一个 } 之间的内容（容忍前后多余文字）
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"无法定位 JSON 边界: {raw[:100]}")
    return json.loads(text[start : end + 1])


def _validate_annotation(
    parsed: Dict[str, Any],
    segment_start: int,
    segment_end: int,
    current_heading_count: int,
) -> Tuple[_AnnotationResult, str]:
    """
    防线 3 + 防线 4：校验 LLM 返回的 add/remove 是否合理。

    返回 (校验后的结果, 状态消息)。状态消息仅用于日志，不代表失败。
    严重不合理（如数量护栏超限、JSON 结构错误）抛异常。
    """
    if not isinstance(parsed, dict):
        raise ValueError("JSON 根不是对象")

    raw_add = parsed.get("add") or []
    raw_remove = parsed.get("remove") or []

    if not isinstance(raw_add, list) or not isinstance(raw_remove, list):
        raise ValueError("add / remove 字段必须是数组")

    segment_size = segment_end - segment_start + 1
    add_limit = max(int(segment_size * _ADD_RATIO_LIMIT), 3)  # 至少允许 3 个，避免短段太严
    remove_limit = max(int(current_heading_count * _REMOVE_RATIO_LIMIT), 1) if current_heading_count > 0 else 0

    # 防线 3：数量护栏（防 LLM 失控滥标）
    if len(raw_add) > add_limit:
        raise ValueError(f"add 数量超限 {len(raw_add)} > {add_limit}（段大小 {segment_size}）")
    if len(raw_remove) > remove_limit:
        raise ValueError(f"remove 数量超限 {len(raw_remove)} > {remove_limit}（当前标题 {current_heading_count}）")

    # 防线 4：逐项校验 + 越界过滤
    add_clean: List[Tuple[int, int]] = []
    for item in raw_add:
        if not isinstance(item, dict):
            continue
        line = item.get("line")
        level = item.get("level")
        if not isinstance(line, int) or not isinstance(level, int):
            continue
        if level not in (1, 2, 3):
            continue
        if not (segment_start <= line <= segment_end):
            continue  # 越界丢弃
        add_clean.append((line, level))

    remove_clean: List[int] = []
    for line in raw_remove:
        if not isinstance(line, int):
            continue
        if not (segment_start <= line <= segment_end):
            continue
        remove_clean.append(line)

    msg = f"add={len(add_clean)} remove={len(remove_clean)}"
    return _AnnotationResult(add=add_clean, remove=remove_clean), msg


def _apply_annotation(lines: List[str], anno: _AnnotationResult, offset: int) -> List[str]:
    """
    防线 5：应用 LLM 的标注到原文行（仅修改行首的 # 前缀，绝不动文字本身）

    :param lines: 原始行列表（会被修改并返回）
    :param anno: 已校验的标注结果
    :param offset: 第一行的绝对行号
    :return: 修订后的行列表
    """
    out = list(lines)

    # 应用 remove：移除行首的 # 前缀（保留前缀后的所有文字）
    for line_no in anno.remove:
        idx = line_no - offset
        if not (0 <= idx < len(out)):
            continue
        m = _HEADING_PREFIX_RE.match(out[idx].lstrip())
        if not m:
            continue  # 当前行本来就没 # 前缀，无需移除
        # 找到首个非空白字符的位置，从那里开始去 #
        leading_ws_len = len(out[idx]) - len(out[idx].lstrip())
        out[idx] = out[idx][:leading_ws_len] + out[idx][leading_ws_len + len(m.group(0)):]

    # 应用 add：在行首加 # 前缀（如果该行已有 # 前缀则跳过，避免 ## 变 ### 这种意外）
    for line_no, level in anno.add:
        idx = line_no - offset
        if not (0 <= idx < len(out)):
            continue
        stripped = out[idx].lstrip()
        if not stripped:
            continue  # 空行跳过
        if _HEADING_PREFIX_RE.match(stripped):
            continue  # 已有标题前缀，跳过避免叠加
        prefix = "#" * level + " "
        leading_ws_len = len(out[idx]) - len(stripped)
        out[idx] = out[idx][:leading_ws_len] + prefix + out[idx][leading_ws_len:]

    return out


def _split_into_segments(lines: List[str], segment_size: int = _SEGMENT_LINES) -> List[Tuple[int, int]]:
    """
    把行列表切成多段（每段 segment_size 行），返回每段的 [start, end] 绝对行号区间（含两端，1 起算）。
    """
    if not lines:
        return []
    segments: List[Tuple[int, int]] = []
    n = len(lines)
    cursor = 0
    while cursor < n:
        end = min(cursor + segment_size, n)
        segments.append((cursor + 1, end))  # 行号从 1 起
        cursor = end
    return segments


# ---------- 主类 ----------

class LLMDocumentAnnotator:
    """LLM 文档结构标注式修订器（标注式，6 道防线）"""

    def __init__(self, segment_lines: int = _SEGMENT_LINES):
        self.segment_lines = segment_lines
        self._llm = get_llm_fast()

    def clean(self, text: str) -> str:
        """
        对启发式 Markdown 做标注式修订。

        - 输入文本任何字符都不会被 LLM 改动
        - LLM 仅决定"哪些行的 # 前缀该加 / 该去"
        - 单段失败回退到该段原文（不影响其他段）

        :param text: 启发式解析后的 Markdown
        :return: 修订后的 Markdown
        """
        if not text or not text.strip():
            return text

        lines = text.split("\n")
        segments = _split_into_segments(lines, self.segment_lines)
        logger.info(
            "LLM 标注开始：原文 {} 行 / {} 字符，切为 {} 段",
            len(lines), len(text), len(segments),
        )

        revised = list(lines)  # 在副本上累计修订
        ok_count = 0
        skip_count = 0
        total_add = 0
        total_remove = 0

        for idx, (start, end) in enumerate(segments):
            seg_lines = revised[start - 1 : end]
            try:
                anno = self._annotate_segment(seg_lines, start, end)
                # 应用到 revised（按绝对行号）
                segment_revised = _apply_annotation(seg_lines, anno, start)
                revised[start - 1 : end] = segment_revised
                ok_count += 1
                total_add += len(anno.add)
                total_remove += len(anno.remove)
                logger.info(
                    "LLM 标注 {}/{} ✓ add={} remove={}",
                    idx + 1, len(segments), len(anno.add), len(anno.remove),
                )
            except Exception as e:
                # 防线 6：异常 → 整段保留原文（revised 中已经是原文，无需操作）
                skip_count += 1
                logger.warning(
                    "LLM 标注段 {}/{} 失败，保留原文: {}",
                    idx + 1, len(segments), e,
                )

        result = "\n".join(revised)
        logger.info(
            "LLM 标注完成：成功 {}/{} 段，跳过 {} 段；累计补充 {} 个标题，移除 {} 个误标",
            ok_count, len(segments), skip_count, total_add, total_remove,
        )
        return result

    def _annotate_segment(
        self,
        seg_lines: List[str],
        segment_start: int,
        segment_end: int,
    ) -> _AnnotationResult:
        """
        对单段调用 LLM 获取标注。任何阶段失败抛异常（由调用方降级）。
        """
        display = _build_display_lines(seg_lines, segment_start)
        # 统计当前段内已有的标题数（用于 remove 数量护栏）
        current_heading_count = sum(
            1 for ln in seg_lines if _HEADING_PREFIX_RE.match(ln.lstrip())
        )

        messages = [
            {"role": "system", "content": _ANNOTATOR_SYSTEM_PROMPT},
            {"role": "user", "content": _ANNOTATOR_USER_PROMPT_TEMPLATE.format(display=display)},
        ]
        # response_format=json_object 强制 LLM 输出合法 JSON
        raw = self._llm.complete(
            messages,
            temperature=0.1,
            max_tokens=2048,  # JSON 输出很短，2048 足够
            response_format={"type": "json_object"},
        )

        # 防线 2：JSON 解析
        parsed = _parse_llm_json(raw)
        # 防线 3 + 4：校验 + 越界过滤
        anno, _ = _validate_annotation(
            parsed, segment_start, segment_end, current_heading_count
        )
        return anno


# ---------- 模块级便捷函数 ----------

def clean_document_with_llm(text: str) -> str:
    """LLM 标注式修订入口（保持旧 API 命名兼容 document_tasks.py）"""
    return LLMDocumentAnnotator().clean(text)
