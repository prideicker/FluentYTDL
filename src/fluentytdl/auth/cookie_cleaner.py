"""
Cookie 清洗与合规过滤模块

负责对提取的 Cookie 进行隐私合规清洗，仅保留特定平台运行所需的最小化 Cookie 集合。
"""

from __future__ import annotations

from typing import Any, Set

from ..utils.logger import logger

class CookieCleaner:
    """Cookie 清洗器"""

    # 平台域名白名单
    PLATFORM_DOMAINS = {
        "youtube": {".youtube.com", "youtube.com", ".google.com", "google.com"},
        "bilibili": {".bilibili.com", "bilibili.com"},
        "twitter": {".twitter.com", ".x.com", "twitter.com", "x.com"},
    }

    # YouTube 核心 Cookie 白名单 (严格匹配)
    YOUTUBE_ALLOWED_NAMES = {
        # 身份认证
        "SID", "HSID", "SSID", "APISID", "SAPISID",
        # 安全认证 (关键)
        "__Secure-1PSID", "__Secure-3PSID",
        "__Secure-1PAPISID", "__Secure-3PAPISID",
        # 会话状态
        "LOGIN_INFO",
        # 用户偏好
        "PREF",
        # 设备/访客标识
        "VISITOR_INFO1_LIVE",
    }

    # 标准 Netscape Cookie 字段
    NETSCAPE_FIELDS = {"domain", "path", "secure", "expires", "name", "value"}

    @classmethod
    def clean(cls, cookies: list[dict[str, Any]], platform: str = "youtube") -> list[dict[str, Any]]:
        """
        清洗 Cookie 列表
        
        1. 过滤非白名单域名
        2. (YouTube) 过滤非白名单 Cookie Name
        3. 移除多余字段
        
        Args:
            cookies: 原始 Cookie 列表
            platform: 平台标识 (youtube, bilibili 等)
            
        Returns:
            清洗后的 Cookie 列表
        """
        if not cookies:
            return []
            
        cleaned = []
        allowed_domains = cls.PLATFORM_DOMAINS.get(platform, set())
        allowed_names = cls.YOUTUBE_ALLOWED_NAMES if platform == "youtube" else None
        
        ignored_domains: Set[str] = set()
        ignored_names: Set[str] = set()
        
        for cookie in cookies:
            # 1. 域名过滤
            domain = cookie.get("domain", "")
            if allowed_domains and domain not in allowed_domains:
                # 尝试模糊匹配 (如 .google.com 匹配)
                if not any(domain.endswith(d) or d.endswith(domain) for d in allowed_domains):
                    ignored_domains.add(domain)
                    continue
            
            # 2. Name 过滤 (仅限 YouTube)
            name = cookie.get("name", "")
            if allowed_names is not None and name not in allowed_names:
                ignored_names.add(name)
                continue
                
            # 3. 字段清洗 (仅保留 Netscape 标准字段)
            clean_cookie = {
                k: v for k, v in cookie.items() 
                if k in cls.NETSCAPE_FIELDS
            }
            
            # 确保必要字段存在
            if "domain" not in clean_cookie:
                clean_cookie["domain"] = domain
            if "flag" not in clean_cookie:
                 # 自动推断 flag (如果 domain 以 . 开头则为 TRUE)
                 clean_cookie["flag"] = "TRUE" if clean_cookie.get("domain", "").startswith(".") else "FALSE"
            
            cleaned.append(clean_cookie)
            
        # 日志记录清洗结果
        if len(cleaned) < len(cookies):
            logger.info(
                f"[{platform}] Cookie 清洗完成: {len(cookies)} -> {len(cleaned)} "
                f"(移除: {len(cookies) - len(cleaned)})"
            )
            if ignored_domains:
                logger.debug(f"已过滤域名: {', '.join(list(ignored_domains)[:5])}等")
            if ignored_names:
                logger.debug(f"已过滤无关 Cookie: {', '.join(list(ignored_names)[:10])}等")
        else:
            logger.debug(f"[{platform}] Cookie 清洗完成: 无需过滤")
            
        return cleaned
