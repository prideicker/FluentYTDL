import re
from typing import Any

from ..models.errors import DiagnosedError, ErrorCode

# ==================== 错误匹配规则引擎 ====================
ERROR_RULES = [
    {
        "condition": "regex",
        "value": r"Sign in to confirm you're not a bot|Sign in to confirm youre not a bot|Error solving n challenge|poToken",
        "error_code": ErrorCode.POTOKEN_FAILURE,
        "severity": "fatal",
        "fix_action": "switch_proxy",
        "title": "人机验证拦截 (Bot 检测)",
        "message": "YouTube 认为当前请求来自自动化工具。这通常是因为节点 IP 触发了风控，或者 Cookie 被限制。",
        "recovery_hint": "去更换代理节点",
    },
    {
        "condition": "regex",
        "value": r"Members only content",
        "error_code": ErrorCode.LOGIN_REQUIRED,
        "severity": "fatal",
        "fix_action": "extract_cookie",
        "title": "会员专属视频",
        "message": "这是 YouTube 频道的会员专享内容，请确保使用的 Cookie 关联的账号已购买该频道会员。",
        "recovery_hint": "重新导入 Cookie",
    },
    {
        "condition": "regex",
        "value": r"Sign in to confirm your age",
        "error_code": ErrorCode.LOGIN_REQUIRED,
        "severity": "fatal",
        "fix_action": "extract_cookie",
        "title": "年龄限制 (需要登录验证)",
        "message": "该视频有年龄限制，必须使用已验证年龄的 YouTube 账号才能访问。",
        "recovery_hint": "导入 Cookie",
    },
    {
        "condition": "regex",
        "value": r"Private video|This video is only available to registered users",
        "error_code": ErrorCode.LOGIN_REQUIRED,
        "severity": "fatal",
        "fix_action": "extract_cookie",
        "title": "私人视频",
        "message": "该视频已被上传者设置为私有，必须拥有观看权限的账号才能访问。",
        "recovery_hint": "导入 Cookie",
    },
    {
        "condition": "regex",
        "value": r"Sign in to confirm",
        "error_code": ErrorCode.LOGIN_REQUIRED,
        "severity": "fatal",
        "fix_action": "extract_cookie",
        "title": "需要登录验证",
        "message": "YouTube 要求您登录以确认身份。可能是 Cookie 已失效，或者遇到了权限验证。",
        "recovery_hint": "重新导入 Cookie",
    },
    {
        "condition": "regex",
        "value": r"Connection reset by peer|Connection refused|Connection timed out|Read timed out|Timed out",
        "error_code": ErrorCode.NETWORK_ERROR,
        "severity": "recoverable",
        "fix_action": "switch_proxy",
        "title": "网络连接超时或被拒绝",
        "message": "无法与 YouTube 服务器建立连接，通常是网络环境或代理节点问题。",
        "recovery_hint": "检查代理设置",
    },
    {
        "condition": "regex",
        "value": r"CERTIFICATE_VERIFY_FAILED|ssl\.SSLCertVerificationError|certificate verify failed",
        "error_code": ErrorCode.NETWORK_ERROR,
        "severity": "recoverable",
        "fix_action": "switch_proxy",
        "title": "SSL 证书验证失败",
        "message": "HTTPS 连接被干扰，证书无法通过验证。可能是代理软件篡改了证书或网络被劫持。",
        "recovery_hint": "检查代理配置",
    },
    {
        "condition": "regex",
        "value": r"urlopen error|URLError|Name or service not known|getaddrinfo failed|Errno 11001",
        "error_code": ErrorCode.NETWORK_ERROR,
        "severity": "recoverable",
        "fix_action": "switch_proxy",
        "title": "DNS 解析失败",
        "message": "无法解析 YouTube 的域名，通常是 DNS 被污染或网络不通。",
        "recovery_hint": "检查网络或代理",
    },
    {
        "condition": "regex",
        "value": r"HTTP Error 429|Too Many Requests",
        "error_code": ErrorCode.RATE_LIMITED,
        "severity": "recoverable",
        "fix_action": "switch_proxy",
        "title": "请求频率过高 (429 限流)",
        "message": "短时间内请求过多，被临时限流保护。通常在停止请求后的 2-12 小时内会自动恢复。",
        "recovery_hint": "更换节点/稍后重试",
    },
    {
        "condition": "regex",
        "value": r"proxy|ProxyError|Cannot connect to proxy|SOCKSHTTPSConnectionPool",
        "error_code": ErrorCode.NETWORK_ERROR,
        "severity": "recoverable",
        "fix_action": "switch_proxy",
        "title": "代理连接失败",
        "message": "无法连接到配置的代理服务器。",
        "recovery_hint": "检查代理设置",
    },
    {
        "condition": "regex",
        "value": r"HTTP Error 403|forbidden",
        "error_code": ErrorCode.HTTP_ERROR,
        "severity": "fatal",
        "fix_action": "switch_proxy",
        "title": "IP/节点被风控 (403)",
        "message": "YouTube 拒绝了请求。通常是因为代理节点 IP 被临时封锁，与组件版本无关。",
        "recovery_hint": "更换代理节点",
    },
    {
        "condition": "regex",
        "value": r"Video unavailable in your country|Geo-restricted",
        "error_code": ErrorCode.GEO_RESTRICTED,
        "severity": "fatal",
        "fix_action": "switch_proxy",
        "title": "地区限制",
        "message": "由于版权或区域限制，当前网络节点无法访问该视频。",
        "recovery_hint": "更换代理节点",
    },
    {
        "condition": "regex",
        "value": r"Premiere",
        "error_code": ErrorCode.GENERAL,
        "severity": "fatal",
        "fix_action": None,
        "title": "首映未开始",
        "message": "该视频属于首映状态，尚未正式开启播放或您没有观看权限。",
        "recovery_hint": "",
    },
    {
        "condition": "regex",
        "value": r"Requested format is not available",
        "error_code": ErrorCode.FORMAT_UNAVAILABLE,
        "severity": "warning",
        "fix_action": None,
        "title": "无可用视频流",
        "message": "选择的画质、音质或格式在当前视频中不存在。",
        "recovery_hint": "",
    },
    {
        "condition": "regex",
        "value": r"ffprobe/ffmpeg not found|ffmpeg isn't installed",
        "error_code": ErrorCode.GENERAL,
        "severity": "fatal",
        "fix_action": None,  # Can add install ffmpeg action later
        "title": "缺少核心组件 (FFmpeg)",
        "message": "视频合并或封面处理需要 FFmpeg，但系统未找到该工具。",
        "recovery_hint": "",
    },
    {
        "condition": "regex",
        "value": r"No space left on device",
        "error_code": ErrorCode.DISK_FULL,
        "severity": "fatal",
        "fix_action": "open_settings",
        "title": "磁盘空间不足",
        "message": "当前下载目录所在的分区没有足够的剩余空间。",
        "recovery_hint": "清理磁盘/更换路径",
    },
]


def diagnose_error(exit_code: int, stderr: str, parsed_json: dict[str, Any] | None = None) -> DiagnosedError:
    """
    核心诊断函数：根据退出码、错误输出和 JSON 结构，生成诊断对象。
    """
    if not stderr:
        stderr = "未知错误，无输出"

    clean_msg = " ".join(stderr.splitlines())

    # 1. JSON 层级判断（如果有传入解析好的 JSON 错误快照，未来可扩展）
    if parsed_json and isinstance(parsed_json, dict):
        err_type = parsed_json.get("error", {}).get("_type")
        if err_type == "premium_only":
            return DiagnosedError(
                code=ErrorCode.LOGIN_REQUIRED,
                severity="fatal",
                user_title="会员专属视频",
                user_message="这是会员专享内容，请确保账号已购买频道会员。",
                fix_action="extract_cookie",
                technical_detail=f"exit_code={exit_code}, json_error={err_type}",
                recovery_hint="导入 Cookie",
            )

    # 2. 启发式文本/正则层级判断
    for rule in ERROR_RULES:
        if rule.get("condition") == "regex":
            if re.search(rule["value"], clean_msg, re.IGNORECASE):
                return DiagnosedError(
                    code=rule["error_code"],
                    severity=rule["severity"],  # type: ignore
                    user_title=rule["title"],
                    user_message=rule["message"],
                    fix_action=rule.get("fix_action"),
                    technical_detail=f"exit_code={exit_code}, stderr_snippet='{clean_msg[:150]}...'",
                    recovery_hint=rule.get("recovery_hint", ""),
                )

    # 3. 兜底解析
    fallback = stderr.strip()
    match = re.search(r"ERROR:\s*(.*?)(?:\n|$)", stderr, flags=re.IGNORECASE)
    if match:
        fallback = match.group(1).strip()
    
    if len(fallback) > 100:
        fallback = fallback[:97] + "..."

    return DiagnosedError(
        code=ErrorCode.GENERAL,
        severity="fatal",
        user_title="解析或下载失败",
        user_message="系统遇到无法识别的错误。\n建议检查网络连接或尝试更新核心组件。",
        fix_action=None,
        technical_detail=f"exit_code={exit_code}, stderr='{fallback}'",
        recovery_hint="",
    )


def probe_youtube_connectivity(timeout: float = 5.0) -> bool:
    """
    HEAD 请求 youtube.com 检测网络连通性（不经过 yt-dlp）。
    会自动读取应用内代理配置。
    """
    import urllib.request

    try:
        from ..core.config_manager import config_manager
        proxy_mode = str(config_manager.get("proxy_mode") or "off").lower().strip()
        proxy_url = str(config_manager.get("proxy_url", "") or "").strip()
    except Exception:
        proxy_mode = "off"
        proxy_url = ""

    try:
        req = urllib.request.Request(
            "https://www.youtube.com/",
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        handlers: list = []
        if proxy_mode == "manual" and proxy_url:
            lower = proxy_url.lower()
            if not (lower.startswith("http://") or lower.startswith("https://") or lower.startswith("socks5://")):
                proxy_url = "http://" + proxy_url
            handlers.append(urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url}))
        elif proxy_mode == "system":
            pass
        else:
            handlers.append(urllib.request.ProxyHandler({}))

        opener = urllib.request.build_opener(*handlers)
        resp = opener.open(req, timeout=timeout)
        return resp.status < 400
    except Exception:
        return False

def generate_issue_url(title: str, raw_error: str) -> str:
    """生成预填内容的 GitHub Issue 链接"""
    import urllib.parse
    max_err_len = 1500
    if len(raw_error) > max_err_len:
        raw_error = raw_error[:max_err_len] + "\n...[Truncated]"
    issue_title = urllib.parse.quote(f"[AutoReport] {title}")
    body = f"### 错误描述\n自动捕获到的错误：\n**{title}**\n\n### 错误日志\n```text\n{raw_error}\n```\n\n### 其他信息\n- FluentYTDL 版本: \n- 操作系统: \n"
    issue_body = urllib.parse.quote(body)
    return f"https://github.com/SakuraForgot/FluentYTDL/issues/new?title={issue_title}&body={issue_body}&labels=bug"
