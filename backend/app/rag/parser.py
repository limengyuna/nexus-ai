"""
文档解析器

职责：将多种格式的文档解析为统一的纯文本字符串。
- PDF (.pdf)
- Word (.docx)
- Markdown (.md / .markdown)
- 纯文本 (.txt)

设计：使用工厂模式，对外暴露 `parse_document(path)` 统一接口，
内部按扩展名分发到具体解析器。
"""
from pathlib import Path
from typing import Callable, Dict

from loguru import logger


# ---------- 自定义异常 ----------
class UnsupportedFileTypeError(ValueError):
    """文件类型不支持时抛出"""


class DocumentParseError(RuntimeError):
    """文档解析失败时抛出"""


# ---------- 具体解析器实现 ----------
def _parse_txt(file_path: Path) -> str:
    """解析纯文本文件。尝试 UTF-8，失败则用 GBK 兜底（中文 Windows 常见）。"""
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError(f"无法识别文件编码: {file_path}")


def _parse_markdown(file_path: Path) -> str:
    """解析 Markdown 文件。保留原始 markdown 文本，由后续 splitter 处理结构。"""
    return _parse_txt(file_path)


def _parse_pdf(file_path: Path) -> str:
    """
    解析 PDF 文件，按页拼接文本。

    依赖 pypdf；对扫描版 PDF 无能为力（需 OCR，超出 MVP 范围）。
    """
    # 延迟导入：仅在真正解析 PDF 时引入依赖，避免无 PDF 场景的导入开销
    from pypdf import PdfReader

    reader = PdfReader(str(file_path))
    pages_text = []
    for idx, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
            if text.strip():
                # 用分页标记便于后续追溯来源
                pages_text.append(f"[Page {idx}]\n{text}")
        except Exception as e:
            logger.warning("PDF 第 {} 页解析失败: {}", idx, e)
            continue

    if not pages_text:
        raise DocumentParseError(f"PDF 无可提取文本（可能是扫描件）: {file_path}")
    return "\n\n".join(pages_text)


def _parse_docx(file_path: Path) -> str:
    """解析 Word .docx 文件，按段落拼接。"""
    from docx import Document as DocxDocument  # python-docx

    doc = DocxDocument(str(file_path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]

    # 表格内容也提取出来
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                paragraphs.append(row_text)

    if not paragraphs:
        raise DocumentParseError(f"Word 文档内容为空: {file_path}")
    return "\n\n".join(paragraphs)


# ---------- 扩展名 → 解析函数 映射 ----------
_PARSERS: Dict[str, Callable[[Path], str]] = {
    ".txt": _parse_txt,
    ".md": _parse_markdown,
    ".markdown": _parse_markdown,
    ".pdf": _parse_pdf,
    ".docx": _parse_docx,
}


# ---------- 对外统一接口 ----------
class DocumentParser:
    """文档解析器外观类，方便业务层依赖注入与扩展"""

    @staticmethod
    def supported_extensions() -> list[str]:
        """返回当前支持的文件扩展名列表"""
        return list(_PARSERS.keys())

    @staticmethod
    def is_supported(file_name: str) -> bool:
        """判断文件名（按扩展名）是否被支持"""
        return Path(file_name).suffix.lower() in _PARSERS

    @staticmethod
    def parse(file_path: str | Path) -> str:
        """
        解析文档，返回纯文本

        :raises UnsupportedFileTypeError: 不支持的文件类型
        :raises DocumentParseError: 解析失败
        :raises FileNotFoundError: 文件不存在
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")

        ext = path.suffix.lower()
        parser_fn = _PARSERS.get(ext)
        if parser_fn is None:
            raise UnsupportedFileTypeError(
                f"不支持的文件类型: {ext}（支持的类型: {', '.join(_PARSERS.keys())}）"
            )

        logger.info("开始解析文档: {} (类型: {})", path.name, ext)
        text = parser_fn(path)
        logger.info("解析完成: {} -> {} 字符", path.name, len(text))
        return text


# 函数式 API（与 DocumentParser.parse 等价，便于函数式调用）
def parse_document(file_path: str | Path) -> str:
    """快捷函数，等价于 DocumentParser.parse(file_path)"""
    return DocumentParser.parse(file_path)
