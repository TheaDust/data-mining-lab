"""检查 CDP 不关闭用户浏览器、失败时停止驱动及本地导入接口。"""
import unittest
from unittest.mock import MagicMock, patch
from ..dynamic_crawler import ExistingChrome


class ExistingChromeTests(unittest.TestCase):
    def test_remote_endpoint_rejected(self):
        with self.assertRaises(ValueError):ExistingChrome('http://example.com:9222')

    @patch('task1.crawler.dynamic_crawler.sync_playwright')
    def test_disconnect_keeps_user_browser(self, factory):
        driver=factory.return_value.start.return_value
        browser=driver.chromium.connect_over_cdp.return_value
        browser.contexts=[MagicMock()]
        with ExistingChrome() as session:
            self.assertIs(session.context,browser.contexts[0])
        browser.close.assert_not_called()
        browser.contexts[0].close.assert_not_called()
        driver.stop.assert_called_once()

    @patch('task1.crawler.dynamic_crawler.sync_playwright')
    def test_connection_error_stops_driver(self,factory):
        driver=factory.return_value.start.return_value
        driver.chromium.connect_over_cdp.side_effect=RuntimeError('offline')
        with self.assertRaises(RuntimeError):
            with ExistingChrome():pass
        driver.stop.assert_called_once()


if __name__=='__main__':unittest.main()
