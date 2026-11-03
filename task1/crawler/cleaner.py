"""Task1 基础清洗：保留原始正文，所有删除操作可审计。"""
import html
import re
from collections import Counter

NOISE_LINES = {'详细', '查看详情', '点击查看详情', '分享', '打印', '关闭', '返回顶部', 'Back'}


def clean_with_audit(text: str) -> tuple[str, dict]:
    edits = []
    def substitute(pattern, replacement, value, reason):
        def replace(match):
            edits.append({'reason': reason, 'removed': match.group(0), 'replacement': replacement})
            return replacement
        return re.sub(pattern, replace, value)
    value = html.unescape(text)
    if value != text:
        edits.append({'reason': 'HTML 实体解码', 'before': text[:120], 'after': value[:120]})
    # 仅去除可识别的残留标签，不用泛化尖括号规则误伤正文比较表达式。
    value = substitute(r'</?(?:div|span|p|br|a|strong|em|b|img)\b[^>]*>', '', value, '残留标签')
    value = substitute(r'https?://[^\s<>\u3000\u3002\uff0c\uff1b]+', '', value, '正文中的 URL')
    value = substitute(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b\ufeff]', '', value, '控制或不可见字符')
    lines = []
    for original in value.splitlines():
        line = re.sub(r'\s+', ' ', original).strip()
        if line != original:
            edits.append({'reason': '空白规范化', 'before': original, 'after': line})
        if not line:
            edits.append({'reason': '空行移除', 'removed': original})
            continue
        if line in NOISE_LINES:
            edits.append({'reason': '独立按钮文字', 'removed': line})
            continue
        # 只去相邻的完整长行重复，不全局去重，以免删除不同路线共有的步骤。
        if lines and len(line) >= 20 and line == lines[-1]:
            edits.append({'reason': '相邻长段重复', 'removed': line})
            continue
        lines.append(line)
    result = '\n'.join(lines)
    return result, {'raw_chars': len(text), 'clean_chars': len(result),
                    'counts': dict(Counter(e['reason'] for e in edits)), 'edits': edits}


def clean_text(text: str) -> str:
    return clean_with_audit(text)[0]
