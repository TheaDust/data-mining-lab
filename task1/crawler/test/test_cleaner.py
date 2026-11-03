"""验证基础清洗不会删除路线顺序、时间和景点，且删除操作留痕。"""
import unittest
from ..cleaner import clean_with_audit


class CleanerTests(unittest.TestCase):
    def test_preserve_route_time_and_names(self):
        raw = '  上午9点\xa0午门 → 太和殿\n\n下午2点：御花园 '
        clean, audit = clean_with_audit(raw)
        self.assertEqual(clean, '上午9点 午门 → 太和殿\n下午2点：御花园')
        self.assertTrue(audit['edits'])

    def test_noise_is_exact_line_only(self):
        clean, audit = clean_with_audit('详细\n详细游览说明\nhttps://example.com\n<p>第一天</p>')
        self.assertEqual(clean, '详细游览说明\n第一天')
        self.assertEqual(audit['counts']['独立按钮文字'], 1)

    def test_only_adjacent_long_duplicates(self):
        line = '从午门进入依次参观太和殿中和殿保和殿后前往御花园'
        clean, audit = clean_with_audit(f'{line}\n{line}\n第二天\n{line}')
        self.assertEqual(clean.count(line), 2)
        self.assertEqual(audit['counts']['相邻长段重复'], 1)

    def test_garbled_text_not_guessed(self):
        self.assertEqual(clean_with_audit('未知\ufffd文字')[0], '未知\ufffd文字')


if __name__ == '__main__':
    unittest.main()
