"""
POT Token adapter for unified token acquisition.
"""
from __future__ import annotations

import requests

from PySide6.QtCore import QObject

from ..core.config_manager import config_manager
from ..core.pot_manager import pot_manager
from ..utils.logger import logger


class POTAdapter(QObject):
    """PO Token 统一适配器"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def get_token(self, video_id: str = "") -> str | None:
        """
        获取 PO Token
        
        优先级:
        1. POT Provider 服务 (如果正在运行)
        2. 手动配置的 PO Token
        
        Args:
            video_id: 视频 ID (某些 Provider 可能需要)
            
        Returns:
            PO Token 字符串，如果无法获取则返回 None
        """
        # 1. 尝试 POT Provider 服务
        token = self._get_from_provider(video_id)
        if token:
            logger.info("使用 POT Provider 获取的 Token")
            return token
        
        # 2. 回退到手动配置
        token = self._get_from_config()
        if token:
            logger.info("使用手动配置的 PO Token")
            return token
        
        logger.warning("未能获取 PO Token")
        return None
    
    def _get_from_provider(self, video_id: str) -> str | None:
        """从 POT Provider 服务获取 Token"""
        if not pot_manager.is_running():
            return None
        
        try:
            port = pot_manager.port
            url = f"http://127.0.0.1:{port}/token"
            
            # 某些 provider 需要 video_id
            payload = {}
            if video_id:
                payload["video_id"] = video_id
            
            response = requests.post(url, json=payload, timeout=5)
            
            if response.ok:
                data = response.json()
                return data.get("token") or data.get("potoken")
            
        except requests.exceptions.ConnectionError:
            logger.debug("POT Provider 连接失败")
        except requests.exceptions.Timeout:
            logger.debug("POT Provider 请求超时")
        except Exception as e:
            logger.debug(f"POT Provider 请求失败: {e}")
        
        return None
    
    def _get_from_config(self) -> str | None:
        """从配置中获取手动设置的 Token"""
        token = config_manager.get("youtube_po_token")
        if token and isinstance(token, str) and len(token) > 10:
            return token.strip()
        return None
    
    def is_available(self) -> bool:
        """检查是否有可用的 Token 来源"""
        return pot_manager.is_running() or bool(self._get_from_config())


# 全局单例
pot_adapter = POTAdapter()
