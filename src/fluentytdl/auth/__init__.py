"""
FluentYTDL 认证功能域

包含浏览器 Cookie 提取、验证状态管理等功能。
"""

from .auth_service import AuthService, auth_service, AuthSourceType
from .cookie_manager import CookieManager

__all__ = [
    "AuthService",
    "auth_service",
    "AuthSourceType",
    "CookieManager",
]
