"""按页面模板配置正文和元信息选择器，不在 crawler 中解析站点。"""
import re
from dataclasses import dataclass
from bs4 import BeautifulSoup
from .base_parser import BaseParser


@dataclass(frozen=True)
class Template:
    body: str
    title: str = 'title'
    date: str | None = None
    author: str | None = None


# 按网站模板复用；多区块按 DOM 顺序保留，避免重新排列游览步骤。
TEMPLATES = {
    'dpm_visit': Template('.x-container > div[class^="visit"]'),
    'huangshan_strategy': Template('.article-con', '.raiders-info h1, .raiders-info h2, .raiders-info h3', '.raiders-info p span'),
    'hunan_article': Template('.content', 'h1', 'h1 + *'),
    'jiuzhai_service': Template('[id^="owlcarousel-"]'),
}


class TemplateParser(BaseParser):
    def __init__(self, template: str):
        self.template = TEMPLATES[template]
        self.name = template

    def parse(self, html: str) -> dict:
        soup = BeautifulSoup(html, 'html.parser')
        def value(selector):
            node = soup.select_one(selector) if selector else None
            return node.get_text(' ', strip=True) if node else None
        title = value(self.template.title) or value('title')
        date_text = value(self.template.date)
        # 只读取文章元信息区域，不把正文历史日期、页面时钟当发布时间。
        match = re.search(r'\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?', date_text or '')
        nodes = soup.select(self.template.body)
        if not nodes or not title:
            raise ValueError(f'{self.name}: 标题或正文容器缺失，需复核模板')
        for node in nodes:
            for noise in node.select('script, style, nav, footer, noscript, iframe, .owl-nav, .owl-dots'):
                noise.decompose()
        raw = '\n'.join(node.get_text('\n', strip=False) for node in nodes)
        if not raw.strip():
            raise ValueError(f'{self.name}: 正文为空')
        return dict(title=title, author=value(self.template.author),
                    publish_time=match.group(0) if match else None, raw_text=raw)
