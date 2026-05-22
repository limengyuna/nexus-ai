"""
文档解析器（基于 Unstructured）

职责：将多种格式的文档解析为结构化的 Markdown 文本。

架构：
1. 使用 unstructured 库自动检测文档类型并提取结构化元素（Title, NarrativeText, Table 等）
2. 将元素转换为 Markdown 格式，保留文档结构（标题层级、表格等）
3. 输出统一格式，与 MarkdownHeaderSplitter 配合进行结构化分块

支持格式：.txt, .md, .pdf, .docx, .doc, .html, .pptx, .xlsx 等 20+ 种
"""
import re
from pathlib import Path
from typing import List

from loguru import logger


# ---------- 自定义异常 ----------
class UnsupportedFileTypeError(ValueError):
    """文件类型不支持时抛出"""


class DocumentParseError(RuntimeError):
    """文档解析失败时抛出"""


# ---------- Unstructured 元素转 Markdown ----------
def _elements_to_markdown(elements: List) -> str:
    """
    将 unstructured 的 Element 列表转换为 Markdown 格式文本
    
    元素类型映射：
    - Title → # 标题（根据层级深度决定 # 数量）
    - NarrativeText → 普通段落
    - ListItem → - 列表项
    - Table → Markdown 表格
    - 其他 → 普通文本
    """
    lines: List[str] = []
    
    for elem in elements:
        elem_type = type(elem).__name__
        text = str(elem).strip()
        
        if not text:
            continue
        
        if elem_type == "Title":
            # 根据元数据中的 category_depth 决定标题层级，默认 1 级
            depth = getattr(elem.metadata, "category_depth", 0) or 0
            prefix = "#" * min(max(depth + 1, 1), 4)  # 限制在 1-4 级
            lines.append(f"{prefix} {text}")
        
        elif elem_type == "ListItem":
            lines.append(f"- {text}")
        
        elif elem_type == "Table":
            # 尝试获取 HTML 格式的表格并转换
            html_table = getattr(elem.metadata, "text_as_html", None)
            if html_table:
                lines.append(_html_table_to_markdown(html_table))
            else:
                lines.append(text)
        
        elif elem_type == "Header":
            continue  # 跳过页眉（如"公安部规章"等重复出现的页眉）
        
        elif elem_type == "Footer":
            continue  # 跳过页脚
        
        elif elem_type == "PageBreak":
            continue  # 跳过分页符
        
        else:
            # NarrativeText, Text, UncategorizedText 等
            lines.append(text)
    
    return "\n\n".join(lines)


def _html_table_to_markdown(html: str) -> str:
    """将 HTML 表格转换为简易 Markdown 表格"""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            return html
        
        md_rows = []
        for i, row in enumerate(rows):
            cells = row.find_all(["td", "th"])
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            md_rows.append("| " + " | ".join(cell_texts) + " |")
            
            # 在表头后添加分隔行
            if i == 0:
                md_rows.append("| " + " | ".join(["---"] * len(cells)) + " |")
        
        return "\n".join(md_rows)
    except Exception:
        return html


# ---------- 中文标题检测增强 ----------
# 补偿 Unstructured 对中文章节编号模式的识别不足
_CN_CHAPTER_RE = re.compile(r"^(第[一二三四五六七八九十百零\d]+编)\s*(.*)$")
_CN_SECTION_H1_RE = re.compile(r"^(第[一二三四五六七八九十百零\d]+章)\s*(.*)$")
_CN_SECTION_H2_RE = re.compile(r"^(第[一二三四五六七八九十百零\d]+节)\s*(.*)$")
_CN_ARTICLE_RE = re.compile(r"^(第[一二三四五六七八九十百零\d]+条)\s*(.*)$")
# 触发检测的模式：文本中至少出现 3 个"第X章"或"第X条"
_CN_TRIGGER_RE = re.compile(r"第[一二三四五六七八九十百零\d]+[章条]")


def _enhance_chinese_headings(text: str) -> str:
    """
    中文标题检测增强：识别"第X编/章/节/条"模式，补充 Markdown 标题标记
    
    安全机制：
    1. 阈值触发：至少出现 3 个"第X章"或"第X条"才启用
    2. 跳过已有标题：以 # 开头的行不处理
    3. 行长度限制：只处理 < 30 字的短行（真标题通常很短）
    """
    if len(_CN_TRIGGER_RE.findall(text)) < 3:
        return text
    
    logger.info("检测到中文章节编号模式，启用标题增强")
    
    lines = text.split("\n")
    processed = []
    
    for line in lines:
        stripped = line.strip()
        
        # 空行保留
        if not stripped:
            processed.append("")
            continue
        
        # 已经是标题的跳过
        if stripped.startswith("#"):
            processed.append(stripped)
            continue
        
        # 只处理短行（真正的标题通常 < 30 字）
        if len(stripped) < 30:
            # 按优先级匹配：编 > 章 > 节 > 条
            m = _CN_CHAPTER_RE.match(stripped)
            if m:
                processed.append(f"# {m.group(1)} {m.group(2)}".strip())
                continue
            
            m = _CN_SECTION_H1_RE.match(stripped)
            if m:
                processed.append(f"# {m.group(1)} {m.group(2)}".strip())
                continue
            
            m = _CN_SECTION_H2_RE.match(stripped)
            if m:
                processed.append(f"## {m.group(1)} {m.group(2)}".strip())
                continue
            
            m = _CN_ARTICLE_RE.match(stripped)
            if m:
                processed.append(f"### {m.group(1)} {m.group(2)}".strip())
                continue
        
        processed.append(stripped)
    
    return "\n".join(processed)


# ---------- Unstructured 支持的扩展名 ----------
# 部分格式（.doc, .ppt, .xls, .odt, .rtf）需要系统安装 LibreOffice
_SUPPORTED_EXTENSIONS = {
    ".txt", ".md", ".markdown",  # 文本类
    ".pdf",                       # PDF
    ".docx", ".doc",              # Word
    ".pptx", ".ppt",              # PowerPoint
    ".xlsx", ".xls", ".csv",      # 表格
    ".html", ".htm",              # 网页
    ".xml", ".json",              # 结构化数据
    ".rtf", ".odt",               # 其他文档格式（需要 LibreOffice）
}


def _parse_with_unstructured(file_path: Path) -> str:
    """
    使用 unstructured 库解析文档
    
    自动检测文档类型，提取结构化元素，转换为 Markdown 格式
    """
    from unstructured.partition.auto import partition
    
    try:
        # partition 自动检测文件类型并解析
        elements = partition(filename=str(file_path))
        
        if not elements:
            raise DocumentParseError(f"文档解析结果为空: {file_path}")
        
        # 转换为 Markdown 格式
        markdown_text = _elements_to_markdown(elements)
        
        # 中文标题检测增强（补偿 Unstructured 对中文标题的识别不足）
        markdown_text = _enhance_chinese_headings(markdown_text)
        
        logger.info(
            "Unstructured 解析完成: {} -> {} 个元素 -> {} 字符",
            file_path.name, len(elements), len(markdown_text)
        )
        return markdown_text
        
    except Exception as e:
        # 如果 unstructured 失败，尝试用简单的文本读取兜底
        if file_path.suffix.lower() in {".txt", ".md", ".markdown"}:
            logger.warning("Unstructured 解析失败，回退到纯文本读取: {}", e)
            return _fallback_text_parse(file_path)
        raise DocumentParseError(f"文档解析失败: {file_path} - {e}") from e


def _fallback_text_parse(file_path: Path) -> str:
    """纯文本解析的兜底方案"""
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError(f"无法识别文件编码: {file_path}")


# ---------- 对外统一接口 ----------
class DocumentParser:
    """
    文档解析器（基于 Unstructured）
    
    特性：
    - 支持 50+ 种文档格式
    - 自动检测文档类型
    - 提取结构化元素（标题、段落、表格、列表）
    - 输出 Markdown 格式，保留文档结构
    """

    @staticmethod
    def supported_extensions() -> list[str]:
        """返回当前支持的文件扩展名列表"""
        return sorted(_SUPPORTED_EXTENSIONS)

    @staticmethod
    def is_supported(file_name: str) -> bool:
        """判断文件名（按扩展名）是否被支持"""
        return Path(file_name).suffix.lower() in _SUPPORTED_EXTENSIONS

    @staticmethod
    def parse(file_path: str | Path) -> str:
        """
        解析文档，返回 Markdown 格式文本

        :raises UnsupportedFileTypeError: 不支持的文件类型
        :raises DocumentParseError: 解析失败
        :raises FileNotFoundError: 文件不存在
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        ext = path.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"不支持的文件类型: {ext}（支持的类型: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}）"
            )

        logger.info("开始解析文档: {} (类型: {}, 解析器: Unstructured)", path.name, ext)
        text = _parse_with_unstructured(path)
        logger.info("解析完成: {} -> {} 字符", path.name, len(text))
        return text


# 函数式 API（与 DocumentParser.parse 等价，便于函数式调用）
def parse_document(file_path: str | Path) -> str:
    """快捷函数，等价于 DocumentParser.parse(file_path)"""
    return DocumentParser.parse(file_path)
