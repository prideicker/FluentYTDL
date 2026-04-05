import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import PySide6.QtWidgets as QtWidgets
from src.fluentytdl.download.executor import DownloadExecutor


class TestDownloadWarningMock(unittest.TestCase):
    def setUp(self):
        self.app = QtWidgets.QApplication.instance()
        if not self.app:
            self.app = QtWidgets.QApplication(sys.argv)

    @patch('src.fluentytdl.download.executor.subprocess.Popen')
    def test_warning_parsing(self, MockPopen):
        # 创建伪装的进度和警告输出
        fake_outputs = [
            b"[download] Destination: fake_video.mp4\n",
            b"WARNING: [youtube] no formats available for video; falling back to another format\n",
            b"FLUENTYTDL|__PROGRESS__|10.0|10MiB|1MiB/s|00:10\n",
            b"WARNING: requested format not available\n",
            b"FLUENTYTDL|__PROGRESS__|100.0|100MiB|10MiB/s|00:00\n",
        ]
        
        mock_process = MagicMock()
        mock_process.stdout = fake_outputs
        mock_process.poll.side_effect = [None, None, None, None, None, 0] # 前几次 None 表示仍在运行，之后返回 0
        mock_process.returncode = 0
        MockPopen.return_value = mock_process
        opts = {"format": "best_mp4"}
        executor = DownloadExecutor()
        
        # 覆写 on_status 测试是否接收到警告
        received_warnings = []
        def mock_on_status(msg: str):
            print(f"[TEST DEBUG] on_status: {msg}")
            if "⚠️ " in msg:
                received_warnings.append(msg)
                print(f"[UI 接收到状态]: {msg}")
                
        # Fake cancel check
        def fake_cancel_check(): return False
        
        class DummyStrategy:
            label = "test"
            
        try:
            executor.execute(
                url="https://youtube.com/watch?v=mock_id_456",
                ydl_opts=opts,
                strategy=DummyStrategy(),
                on_progress=lambda d: None,
                on_status=mock_on_status,
                on_path=lambda p: None,
                cancel_check=fake_cancel_check
            )
        except Exception:
            pass
        
        self.assertGreaterEqual(len(received_warnings), 2, "UI 未成功接收到足够数量的抓取警告")
        print("✅ 警告回传测试通过，已提取到了WARNING信息。")


if __name__ == "__main__":
    unittest.main()
