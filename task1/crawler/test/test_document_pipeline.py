"""离线验证 schema 枚举、清洗顺序和模板元信息边界。"""
import unittest
from ..document_pipeline import clean_text, validate_document
from ..parsers.template_parser import TemplateParser


class PipelineTests(unittest.TestCase):
    def test_route_order(self):
        self.assertEqual(clean_text(' 上午9点  午门\n\n→ 太和殿  '), '上午9点 午门\n→ 太和殿')

    def test_article_date_is_not_body_date(self):
        html = '<h1>线路</h1><p>2022-08-16 13:06:13 来源：</p><div class="content">第一天：东门→天子山<p>2021年9月18日</p></div>'
        doc = TemplateParser('hunan_article').parse(html)
        self.assertEqual(doc['publish_time'], '2022-08-16 13:06:13')
        self.assertIsNone(doc['author'])
        self.assertIn('东门→天子山', doc['raw_text'])

    def test_missing_body_rejected(self):
        with self.assertRaises(ValueError):
            TemplateParser('huangshan_strategy').parse('<title>登录</title>')

    def test_bad_document_rejected(self):
        with self.assertRaises(ValueError):
            validate_document({'title': '无正文'})


if __name__ == '__main__':
    unittest.main()
