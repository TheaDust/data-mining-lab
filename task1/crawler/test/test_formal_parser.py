"""正式模板的边界检查，安全提示不得被当作成功文档。"""
import unittest
from ..parsers.formal_parser import FormalParser


class FormalParserTests(unittest.TestCase):
    def test_security_page_rejected(self):
        with self.assertRaises(ValueError):
            FormalParser('xiaohongshu_note').parse('<title>安全限制</title>当前网络存在风险 300012')

    def test_note_order_preserved(self):
        html='<div id="detail-title">游记</div><div id="detail-desc">上午9点午门→太和殿。下午2点御花园。这是游客原本的游览顺序与体验内容。</div>'
        parsed=FormalParser('xiaohongshu_note').parse(html)
        self.assertIn('上午9点午门→太和殿',parsed['raw_text'])
        self.assertIsNone(parsed['author'])

    def test_beijing_date(self):
        html='<h1>故宫路线</h1><li id="time">2017-02-09 15:05:04</li><div class="mod-content"><article>'+('上午午门→太和殿。'*5)+'</article></div>'
        self.assertEqual(FormalParser('visitbeijing_article').parse(html)['publish_time'],'2017-02-09 15:05:04')


if __name__=='__main__':
    unittest.main()
