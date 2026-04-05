import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import PySide6.QtWidgets as QtWidgets
from PySide6.QtCore import QTimer

# 模拟应用所需的环境
from src.fluentytdl.ui.components.download_config_window import DownloadConfigWindow


class TestDownloadConfigWindowMock(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if not self.app:
            self.app = QtWidgets.QApplication(sys.argv)

    @patch('src.fluentytdl.ui.components.download_config_window.InfoExtractWorker')
    def test_low_quality_ui(self, MockWorker):
        # 创建伪造的后端字典形式的数据
        # 故意制造最高只拥有 480p 视频流的数据
        fake_info_dict = {
            "id": "mock_id_123",
            "title": "Low Quality Video Test",
            "uploader": "Test Channel",
            "thumbnail": "",
            "formats": [
                {
                    "format_id": "1",
                    "vcodec": "avc1",
                    "acodec": "none",
                    "height": 480  # 最高只有480p
                },
                {
                    "format_id": "2",
                    "vcodec": "avc1",
                    "acodec": "none",
                    "height": 360
                },
                {
                    "format_id": "3",
                    "vcodec": "none",
                    "acodec": "mp4a",
                    "abr": 128
                }
            ]
        }
        
        # 拦截 worker 的执行并模拟立马返回成功信息
        mock_worker_instance = MagicMock()
        MockWorker.return_value = mock_worker_instance

        window = DownloadConfigWindow(url="https://youtube.com/watch?v=mock_id_123")
        window.show()

        # 模拟工作线程发送完毕信号
        def trigger_fake_success():
            window.on_parse_success(fake_info_dict)
            
        QTimer.singleShot(500, trigger_fake_success)
        
        print("已展示低画质测试窗口，请手动检查是否出现 ⚠️ 警告：该视频受限，最高仅支持480p")
        # 让 GUI 开始执行事件循环以供用户手动测试
        self.app.exec()


if __name__ == "__main__":
    unittest.main()
