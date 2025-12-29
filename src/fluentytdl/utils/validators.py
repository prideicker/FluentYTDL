from __future__ import annotations

import re


class UrlValidator:
    """URL 验证工具类"""

    # 覆盖常见的 YouTube URL 格式 (短链接、标准链接、以及 Shorts)
    YOUTUBE_REGEX = r"^(https?://)?(www\.)?(m\.)?(youtube\.com|youtu\.be)/(watch\?v=|embed/|v/|shorts/|live/)?[\w-]+(\?[\w=&-]*)?$"

    @staticmethod
    def is_youtube_url(text: str) -> bool:
        if not text:
            return False
        return bool(re.match(UrlValidator.YOUTUBE_REGEX, text.strip()))
