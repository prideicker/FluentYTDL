from __future__ import annotations

import re


class UrlValidator:
    """URL 验证工具类"""

    # 覆盖常见的 YouTube URL 格式
    # 视频：watch?v=, embed/, v/, shorts/, live/
    # 频道：@Handle, channel/UCxxx, c/Name, user/Name（含可选标签页后缀）
    # 播放列表：playlist?list=
    # 短链接：youtu.be/xxx
    YOUTUBE_REGEX = (
        r"^(https?://)?(www\.)?(m\.)?(youtube\.com|youtu\.be)/"
        r"("
        r"@[\w.-]+(/(videos|shorts))?"       # 频道 @Handle（含可选标签页）
        r"|channel/[\w-]+(/(videos|shorts))?" # 频道 ID
        r"|c/[\w.-]+(/(videos|shorts))?"      # 旧自定义 URL
        r"|user/[\w.-]+(/(videos|shorts))?"   # 旧用户名
        r"|watch\?v=[\w-]+"                   # 标准视频
        r"|embed/[\w-]+"                      # 嵌入
        r"|v/[\w-]+"                          # 旧格式
        r"|shorts/[\w-]+"                     # Shorts
        r"|live/[\w-]+"                       # 直播
        r"|playlist\?list=[\w-]+"             # 播放列表
        r"|[\w-]+"                            # 短链接 / 其他
        r")"
        r"(\?[\w=&.-]*)?"                     # 可选查询参数
        r"$"
    )

    # 频道 URL 专用正则
    _CHANNEL_REGEX = (
        r"^(https?://)?(www\.)?(m\.)?youtube\.com/"
        r"("
        r"@[\w.-]+(/(videos|shorts))?"
        r"|channel/[\w-]+(/(videos|shorts))?"
        r"|c/[\w.-]+(/(videos|shorts))?"
        r"|user/[\w.-]+(/(videos|shorts))?"
        r")"
        r"(\?[\w=&.-]*)?$"
    )

    @staticmethod
    def is_youtube_url(text: str) -> bool:
        if not text:
            return False
        return bool(re.match(UrlValidator.YOUTUBE_REGEX, text.strip()))

    @staticmethod
    def is_channel_url(text: str) -> bool:
        """判断是否为 YouTube 频道 URL"""
        if not text:
            return False
        return bool(re.match(UrlValidator._CHANNEL_REGEX, text.strip()))
