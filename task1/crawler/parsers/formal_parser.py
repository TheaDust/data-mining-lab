"""正式站点的文章模板及共享小红书 DOM 解析器。无正文时拒绝登录提示页。"""
from bs4 import BeautifulSoup
from .base_parser import BaseParser
import re

FORMAL_NAMES={'visitbeijing_article','hangzhou_article','jiuzhai_article','xiaohongshu_note'}


class FormalParser(BaseParser):
    def __init__(self,name):
        self.name=name

    def parse(self,html):
        soup=BeautifulSoup(html,'html.parser')
        if self.name=='xiaohongshu_note':
            body=soup.select_one('#detail-desc .note-text, #detail-desc, .note-content .desc')
            if body is None:
                visible=soup.get_text(' ',strip=True)
                raise ValueError('无可访问笔记正文；页面提示：'+visible[:250])
            title=soup.select_one('#detail-title, .note-content .title')
            author=soup.select_one('.author-container .username, .author-wrapper .username')
            date=soup.select_one('.note-content .date')
        else:
            selectors={
                'visitbeijing_article':'.mod-content article',
                'hangzhou_article':'.zhengwen',
                'jiuzhai_article':'[id^="imagegrid-"]',
            }
            body=soup.select_one(selectors[self.name])
            title=soup.select_one('h1, .article-title, .article_title') or soup.title
            author=soup.select_one('meta[name="author"]')
            date=soup.select_one('meta[name="PubDate"], meta[property="article:published_time"], time')
            if self.name=='visitbeijing_article':
                date=soup.select_one('li#time')
                # 全站 meta author 可能是页面制作者，优先文章署名栏；空署名不回退猜测。
                author=soup.select_one('li.author')
            if self.name=='hangzhou_article':
                title=soup.select_one('.list_nr .tit')
                date=soup.select_one('.list_nr .tit1')
        if body is None or title is None:
            raise ValueError('文章标题或正文容器缺失，需复核页面模板')
        for noise in body.select('script,style,nav,footer,noscript,.article-info,.share,.pagination'):
            noise.decompose()
        nodes=soup.select('[id^="imagegrid-"]') if self.name=='jiuzhai_article' else [body]
        raw='\n'.join(node.get_text('\n',strip=False) for node in nodes)
        if len(raw.strip())<30:
            raise ValueError('正文过短，不能确认获取了目标内容')
        def text(node):
            return (node.get('content') or node.get_text(' ',strip=True) or None) if node else None
        date_text=text(date)
        match=re.search(r'\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?',date_text or '')
        return dict(title=text(title),author=text(author),publish_time=match.group(0) if match else None,raw_text=raw)
