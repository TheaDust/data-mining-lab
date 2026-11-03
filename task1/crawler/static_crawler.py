"""使用 requests 获取静态网页，不包含站点解析规则。"""

import logging
from collections.abc import Mapping

import requests

logger = logging.getLogger(__name__)


def fetch_bytes(url: str, *, headers: Mapping[str, str] | None = None, timeout: float = 30) -> bytes:
    """下载 PDF 等二进制附件；避免文本解码破坏文件，解析由附件 parser 负责。"""
    try:
        with requests.get(url, headers=headers, timeout=timeout) as response:
            if response.status_code != 200:
                raise requests.HTTPError(f"HTTP {response.status_code}: {url}", response=response)
            logger.info("附件下载成功：%s（%d 字节）", url, len(response.content))
            return response.content
    except requests.RequestException:
        logger.exception("附件下载失败：%s", url)
        raise


def fetch_html(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 15,
) -> str:
    """返回 HTML；超时或请求失败时抛出 requests 异常，非 200 抛出 HTTPError。

    timeout 单位为秒，分别限制连接及读取等待，并非整个请求的总时限。
    """
    logger.info("正在请求静态网页：%s", url)
    try:
        # 使用上下文管理器，确保失败及正常返回时都释放响应资源。
        with requests.get(url, headers=headers, timeout=timeout) as response:
            if response.status_code != 200:
                raise requests.HTTPError(
                    f"期望 HTTP 200，实际为 {response.status_code}: {url}",
                    response=response,
                )
            # 无显式字符集时 requests 可能默认 Latin-1，推断编码以减少中文乱码。
            if "charset=" not in response.headers.get("Content-Type", "").lower():
                response.encoding = response.apparent_encoding or response.encoding
            html = response.text
            logger.info("静态网页获取成功：%s（%d 字符）", url, len(html))
            return html
    except requests.Timeout:
        logger.exception("静态网页请求超时：%s", url)
        raise
    except requests.RequestException:
        # 保留原始异常，使调用方能够区分网络错误和 HTTP 状态错误。
        logger.exception("静态网页请求失败：%s", url)
        raise
