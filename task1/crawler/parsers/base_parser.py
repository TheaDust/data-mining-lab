"""解析器只处理 HTML，不执行网络请求。"""

from abc import ABC, abstractmethod
from typing import Any


class BaseParser(ABC):
    """站点解析器继承此接口，并自行定义输出字段。"""

    @abstractmethod
    def parse(self, html: str) -> dict[str, Any]:
        """将 HTML 转换为结构化字典；可在实现中使用 BeautifulSoup。"""
        raise NotImplementedError
