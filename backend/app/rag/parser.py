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


# ---------- 启发式：判断 Unstructured 的 Title 是否真的是标题 ----------
# 中文 / 英文句末标点（用于判断是否为完整句子）
_SENTENCE_END_PUNCT = "。！？；.!?;"
# 中文括号编号子项（如 "（一）"、"（二）"），属于条款内的列举项，不是标题
_CN_ENUM_ITEM_RE = re.compile(r"^[（(][一二三四五六七八九十百零\d]+[）)]")
# 多级数字编号（1.1 / 1.1.1 / 1.1.1.1），至少含一个点，避免误匹配列表项（如 "1.活动"）。
# 常见于学术论文 / 技术文档（如 "4.3 数据库设计"、"4.3.1 E-R 图"）。
_NUM_HEADING_RE = re.compile(r"^\d+\.\d+(?:\.\d+){0,2}\s*\S")


def _is_likely_real_title(text: str, max_len: int = 50) -> bool:
    """
    启发式判断一段文本是否为"真标题"

    背景：Unstructured 在中文 PDF 上 Title 分类不准，常把粗体段落、行首带数字
    编号的段落、甚至字号稍大的正文都判为 Title，导致分块过度碎片化。

    判定规则（按优先级）：
      1. 长度兜底：超过 max_len 字符一定不是标题
      2. 强信号：匹配中文章节模式（第X编/章/节）→ 真标题
      3. 强信号：匹配数字层级（1. / 1.1 / 1.1.1）→ 真标题
      4. 排除项：以中文括号编号开头（（一）（二））→ 是列举项不是标题
      5. 弱信号：短行（< 30 字）且不以句末标点结尾 → 视为标题
      6. 其他默认：当作正文处理
    """
    stripped = text.strip()
    if not stripped or len(stripped) > max_len:
        return False

    # 强信号：中文章节关键字
    if (_CN_CHAPTER_RE.match(stripped) or
            _CN_SECTION_H1_RE.match(stripped) or
            _CN_SECTION_H2_RE.match(stripped)):
        return True

    # 强信号：数字层级编号
    if _NUM_HEADING_RE.match(stripped):
        return True

    # 排除项：（一）（二）这种条款内列举项
    if _CN_ENUM_ITEM_RE.match(stripped):
        return False

    # 弱信号：短行 + 不以句末标点结尾
    if len(stripped) < 30 and stripped[-1] not in _SENTENCE_END_PUNCT:
        # 进一步排除：含多个逗号的多半是不完整句子片段，非标题
        if stripped.count("，") + stripped.count(",") <= 1:
            return True

    return False


def _get_chinese_title_depth(text: str) -> int | None:
    """
    根据标题模式返回深度。返回值与 Markdown 前缀对应关系：
      0 → #   (h1)
      1 → ##  (h2)
      2 → ### (h3)

    层级映射（平衡 「中文章节 + 数字层级」 混合文档，避免同级冲突）：
      第X编 → # (h1)        编与章同级，编被章覆盖是可接受损失
      第X章 → # (h1)        让「第4章 系统设计」与「4.3 数据库设计」不同级
      第X节 → ## (h2)       与 X.Y 同级（实际语义也是子小节）
      X.Y → ## (h2)
      X.Y.Z 及以上 → ### (h3)
    匹配不到返回 None，调用方使用默认深度。
    """
    stripped = text.strip()
    if _CN_CHAPTER_RE.match(stripped):
        return 0  # 编
    if _CN_SECTION_H1_RE.match(stripped):
        return 0  # 章（与编同级，冲突量低）
    if _CN_SECTION_H2_RE.match(stripped):
        return 1  # 节
    # 数字层级 1.1 / 1.1.1
    m = _NUM_HEADING_RE.match(stripped)
    if m:
        head = stripped.split(maxsplit=1)[0].rstrip("、.")
        dots = head.count(".")
        # 1 dot → 1 (h2), 2+ dots → 2 (h3)
        return 1 if dots == 1 else 2
    return None


# ---------- Unstructured 元素转 Markdown ----------
def _elements_to_markdown(elements: List) -> str:
    """
    将 unstructured 的 Element 列表转换为 Markdown 格式文本

    元素类型映射：
    - Title → 经启发式过滤后才加 # 前缀（避免中文 PDF 误识别）
    - NarrativeText → 普通段落
    - ListItem → - 列表项
    - Table → Markdown 表格
    - 其他 → 普通文本
    """
    lines: List[str] = []
    fake_title_count = 0  # 统计被启发式过滤掉的伪标题数（用于日志观察）

    for elem in elements:
        elem_type = type(elem).__name__
        text = str(elem).strip()

        if not text:
            continue

        if elem_type == "Title":
            # 启发式判定：是真标题才加 # 前缀，否则降级为正文
            if _is_likely_real_title(text):
                # 优先用中文章节模式确定层级，其次用 Unstructured 的 category_depth
                cn_depth = _get_chinese_title_depth(text)
                if cn_depth is not None:
                    depth = cn_depth
                else:
                    depth = getattr(elem.metadata, "category_depth", 0) or 0
                prefix = "#" * min(max(depth + 1, 1), 4)  # 限制在 1-4 级
                lines.append(f"{prefix} {text}")
            else:
                # 伪标题降级为普通段落，避免下游分块过度碎片化
                fake_title_count += 1
                lines.append(text)

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
# 注意："第X条" 不再当作 Markdown 标题（避免单条粒度切分导致碎片化），
# 而是作为正文内容保留，依赖最小块合并将多个连续短条款聚合到同一块。
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
            # 按优先级匹配：编 > 章 > 节 > X.Y[.Z]（条不作为标题，保留为内容）
            # 层级映射与 _get_chinese_title_depth 保持一致：
            #   编/章 → # (h1)， 节 → ## (h2)
            #   X.Y → ## (h2)， X.Y.Z+ → ### (h3)
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

            # 数字层级（1.1 / 1.1.1）—— 补偿 Unstructured 未识别为 Title 的伪标题
            m = _NUM_HEADING_RE.match(stripped)
            if m:
                head = stripped.split(maxsplit=1)[0].rstrip("、.")
                dots = head.count(".")
                prefix = "##" if dots == 1 else "###"
                processed.append(f"{prefix} {stripped}")
                continue

            # "第X条" 不升级为标题：法律条款数量极多，单条作标题会导致分块碎片化，
            # 让 splitter 在「章 / 节」层级切分，再由最小块合并将连续短条款聚合

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
        
        # 转换为 Markdown 格式（含 Title 启发式过滤）
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


def _parse_pdf_with_pypdf(file_path: Path) -> str:
    """
    轻量 PDF 文本抽取。

    适合文字型 PDF、简历、报告、财报正文。它不做 OCR / 版面识别，
    但内存占用远低于 unstructured[pdf]，更适合 Railway 低内存环境。
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise DocumentParseError("缺少 pypdf 依赖，请先安装 requirements.txt") from e

    try:
        reader = PdfReader(str(file_path))
        page_count = len(reader.pages)
        logger.info("PyPDF 开始解析: {} pages={}", file_path.name, page_count)

        page_texts: List[str] = []
        for idx, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as e:
                logger.warning("PyPDF 第 {} 页提取失败: {}", idx, e)
                text = ""
            text = text.strip()
            if text:
                page_texts.append(f"## Page {idx}\n\n{text}")

        markdown_text = "\n\n".join(page_texts).strip()
        markdown_text = _enhance_chinese_headings(markdown_text)
        if len(markdown_text) < 20:
            raise DocumentParseError(
                "PDF 轻量文本抽取结果过少，可能是扫描件或图片型 PDF；"
                "Railway 低内存环境不再自动回退重型 OCR 解析。"
            )

        logger.info(
            "PyPDF 解析完成: {} -> {} 页 -> {} 字符",
            file_path.name, page_count, len(markdown_text),
        )
        return markdown_text
    except DocumentParseError:
        raise
    except Exception as e:
        raise DocumentParseError(f"PDF 轻量解析失败: {file_path} - {e}") from e


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

        if ext == ".pdf":
            logger.info("开始解析文档: {} (类型: {}, 解析器: PyPDF)", path.name, ext)
            text = _parse_pdf_with_pypdf(path)
            logger.info("解析完成: {} -> {} 字符", path.name, len(text))
            return text

        logger.info("开始解析文档: {} (类型: {}, 解析器: Unstructured)", path.name, ext)
        text = _parse_with_unstructured(path)
        logger.info("解析完成: {} -> {} 字符", path.name, len(text))
        return text


# 函数式 API（与 DocumentParser.parse 等价，便于函数式调用）
def parse_document(file_path: str | Path) -> str:
    """快捷函数，等价于 DocumentParser.parse(file_path)"""
    return DocumentParser.parse(file_path)
