"""使用本机 Google Chrome 获取动态页面渲染后的 HTML。"""

import logging
from pathlib import Path

from playwright.sync_api import Error, TimeoutError, sync_playwright

logger = logging.getLogger(__name__)


class ExistingChrome:
    """连接用户主动开启的 CDP 会话，只管理本工具新建的标签页。"""

    def __init__(self, endpoint: str = 'http://127.0.0.1:9222'):
        from urllib.parse import urlsplit
        parts = urlsplit(endpoint)
        if parts.hostname not in {'127.0.0.1', 'localhost', '::1'}:
            raise ValueError('仅允许本机 CDP 地址')
        self.endpoint = endpoint

    def __enter__(self):
        self.driver = sync_playwright().start()
        try:
            self.browser = self.driver.chromium.connect_over_cdp(self.endpoint, timeout=5000)
            if not self.browser.contexts:
                raise RuntimeError('Chrome 没有已有 context；请先在该实例正常打开并登录网站')
            self.context = self.browser.contexts[0]
            return self
        except Exception:
            self.driver.stop()
            raise

    def __exit__(self, *args):
        # 只断开本地驱动，不能关闭用户浏览器或已有 context/标签页。
        self.driver.stop()

    def fetch_html(self, url: str, *, snapshot_path: Path, timeout: float = 30000) -> str:
        page = self.context.new_page()
        try:
            page.goto(url, wait_until='domcontentloaded', timeout=timeout)
            # 用真实正文可见性作为完成条件，不等待持续后台请求的 networkidle。
            page.wait_for_function("""() => {
                const message = document.body?.innerText || '';
                const body = document.querySelector('#detail-desc .note-text, #detail-desc, .note-content .desc');
                return /300012|安全限制|验证码/.test(message) ||
                    (body && body.getBoundingClientRect().height > 0 && body.innerText.trim().length >= 30);
            }""", timeout=timeout)
            visible = page.locator('body').inner_text()
            if any(marker in visible for marker in ('300012', '安全限制', '验证码')):
                raise ValueError('页面要求安全验证或存在安全限制，停止采集：'+visible[:250])
            body = page.locator('#detail-desc .note-text, #detail-desc, .note-content .desc').first
            if not body.is_visible() or len(body.inner_text().strip()) < 30:
                raise ValueError('没有可见的有效笔记正文（可能需要登录）')
            return page.content()
        finally:
            try:
                snapshot_path.write_text(page.content(), encoding='utf-8')
            finally:
                page.close()


def fetch_html(
    url: str,
    *,
    headless: bool = True,
    timeout: float = 30_000,
    wait_selector: str | None = None,
    snapshot_path: str | Path | None = None,
) -> str:
    """返回渲染后的 HTML；timeout 单位为毫秒，失败时保留 Playwright 异常。

    默认等待 load；异步内容可通过 wait_selector 指定就绪标记。
    """
    logger.info("正在请求动态网页：%s", url)
    try:
        with sync_playwright() as playwright:
            # 仅使用已安装的 Chrome；缺失时报告错误，不回退或下载 Chromium。
            browser = playwright.chromium.launch(channel="chrome", headless=headless)
            try:
                context = browser.new_context()
                try:
                    page = context.new_page()
                    try:
                        response = page.goto(url, wait_until="load", timeout=timeout)
                        if response is None or response.status != 200:
                            status = response.status if response else "无 HTTP 响应"
                            raise Error(f"期望 HTTP 200，实际为 {status}: {url}")
                        # 持续连接的页面可能永不 networkidle，使用具体元素作为可选就绪条件。
                        if wait_selector:
                            page.wait_for_selector(wait_selector, timeout=timeout)
                        html = page.content()
                        logger.info("动态网页获取成功：%s（%d 字符）", url, len(html))
                        return html
                    finally:
                        # 正式采集保留失败页面，便于区分登录提示、失效链接和正文缺失。
                        if snapshot_path is not None:
                            try:
                                Path(snapshot_path).write_text(page.content(), encoding='utf-8')
                            except Error:
                                logger.warning('无法保存页面快照：%s', url)
                        page.close()
                finally:
                    context.close()
            finally:
                browser.close()
    except TimeoutError:
        logger.exception("动态网页加载超时：%s", url)
        raise
    except Error:
        logger.exception("动态网页获取失败，请检查网址和本机 Chrome：%s", url)
        raise
