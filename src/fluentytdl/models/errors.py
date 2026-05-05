from dataclasses import dataclass
from enum import IntEnum
from typing import Literal


class ErrorCode(IntEnum):
    """全局统一错误码"""
    SUCCESS = 0
    GENERAL = 1
    LOGIN_REQUIRED = 2
    FORMAT_UNAVAILABLE = 3
    HTTP_ERROR = 4
    NETWORK_ERROR = 5
    GEO_RESTRICTED = 6
    EXTRACTOR_ERROR = 7
    POTOKEN_FAILURE = 8
    RATE_LIMITED = 9
    COOKIE_EXPIRED = 10
    DISK_FULL = 11
    UNKNOWN = 99


@dataclass
class DiagnosedError:
    """标准化错误诊断对象"""
    code: ErrorCode
    severity: Literal["fatal", "recoverable", "warning"]
    user_title: str          # 用户看到的简短标题
    user_message: str        # 详细解释与建议
    fix_action: str | None   # 关联 UI 的修复动作（如 relogin, switch_proxy 等）
    technical_detail: str    # 原始错误日志，用于记录
    snapshot_path: str = ""  # 错误现场日志路径（暂留）
    recovery_hint: str = ""  # UI 上按钮的提示词（如“点此重新登录”）

    def to_dict(self) -> dict:
        """支持序列化以便通过 Signal 传递"""
        return {
            "code": self.code.value,
            "severity": self.severity,
            "user_title": self.user_title,
            "user_message": self.user_message,
            "fix_action": self.fix_action,
            "technical_detail": self.technical_detail,
            "snapshot_path": self.snapshot_path,
            "recovery_hint": self.recovery_hint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DiagnosedError":
        """反序列化"""
        return cls(
            code=ErrorCode(data.get("code", 99)),
            severity=data.get("severity", "fatal"),
            user_title=data.get("user_title", "未知错误"),
            user_message=data.get("user_message", "解析错误详情失败"),
            fix_action=data.get("fix_action"),
            technical_detail=data.get("technical_detail", ""),
            snapshot_path=data.get("snapshot_path", ""),
            recovery_hint=data.get("recovery_hint", ""),
        )


class YtDlpExecutionError(Exception):
    """当 yt-dlp 子进程非正常退出时抛出，携带完整的上下文字段以便后续诊断"""
    def __init__(self, exit_code: int, stderr: str, parsed_json: dict | None = None):
        super().__init__(f"yt-dlp 执行失败 (退出码: {exit_code})")
        self.exit_code = exit_code
        self.stderr = stderr
        self.parsed_json = parsed_json or {}
