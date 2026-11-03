"""文本型 PDF 附件解析；不把文件创建时间冒充文章发布时间。"""
from io import BytesIO


class PdfParser:
    def parse(self, data: bytes) -> dict:
        if not data.startswith(b'%PDF-'):
            raise ValueError('响应不是 PDF 文件')
        # 可选轻量依赖，仅成功获取附件时需要；扫描件不自动伪造正文。
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        raw = '\n\n'.join(page.extract_text() or '' for page in reader.pages)
        if not raw.strip():
            raise ValueError('PDF 无文本层，需要单独 OCR 流程')
        title = (reader.metadata.title if reader.metadata else None)
        if not title:
            raise ValueError('PDF 无可靠标题元信息，需复核首页标题')
        return dict(title=title, author=None, publish_time=None, raw_text=raw)
