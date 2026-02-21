import re
from dataclasses import dataclass


@dataclass
class ErrorDefinition:
    keywords: list[str]
    title: str
    description: str
    action: str


# 常见错误特征和对应的中文提示方案
YTDLP_ERRORS = [
    ErrorDefinition(
        keywords=[
            "Sign in to confirm you're not a bot",
            "This video is only available to registered users",
        ],
        title="需要验证 (Cookie 缺失或失效)",
        description="YouTube 限制了对此视频的访问，必须进行身份验证。",
        action="请前往「设置 > 账号验证」，或者直接提取浏览器的 Cookie。",
    ),
    ErrorDefinition(
        keywords=["Video unavailable in your country", "Geo-restricted"],
        title="地区限制 (视频在此国家不可用)",
        description="由于版权或区域限制，当前网络节点无法访问该视频。",
        action="请尝试开启代理，并在「设置 > 网络连接」中配置正确的代理地址，或更换代理节点。",
    ),
    ErrorDefinition(
        keywords=["Members only content"],
        title="会员专属视频",
        description="这是 YouTube 频道的会员专享内容，您的账号尚未加入该频道会员，或者未加载您的会员 Cookie。",
        action="请确保使用的 Cookie 关联的账号已购买该频道会员，并在「设置」中重新提取 Cookie。",
    ),
    ErrorDefinition(
        keywords=["Premiere"],
        title="首映未开始",
        description="该视频属于首映状态，尚未正式开启播放或您没有观看权限。",
        action="请等待视频正式首映后再尝试下载。",
    ),
    ErrorDefinition(
        keywords=["Private video"],
        title="私人视频",
        description="该视频已被上传者设置为私有，必须拥有观看权限的账号才能访问。",
        action="请确认您有权限访问，并更新 Cookie。",
    ),
    ErrorDefinition(
        keywords=["Connection reset by peer", "Timeout", "Connection refused"],
        title="网络连接失败",
        description="无法连接到解析服务器，可能是网络不稳定或被拦截。",
        action="请检查您的代理软件是否运行正常，或者在「设置」中手动配置代理。",
    ),
    ErrorDefinition(
        keywords=["Requested format is not available"],
        title="无可用视频流",
        description="选择的画质、音质或格式在当前视频中不存在。",
        action="请尝试降低清晰度，或选择「自动」模式重新解析。",
    ),
    ErrorDefinition(
        keywords=["ffprobe/ffmpeg not found", "ffmpeg isn't installed"],
        title="缺少核心组件 (FFmpeg)",
        description="视频合并或封面处理需要 FFmpeg，但系统未找到该工具。",
        action="请进入「设置 > 核心组件」，点击安装或更新 FFmpeg。",
    ),
    ErrorDefinition(
        keywords=["No space left on device"],
        title="磁盘空间不足",
        description="当前下载目录所在的分区没有足够的剩余空间。",
        action="请清理磁盘空间，或者在「设置 > 下载选项」中更换下载保存路径。",
    ),
]


def parse_ytdlp_error(error_msg: str) -> tuple[str, str]:
    """
    解析 yt-dlp 或 ffmpeg 的原始错误日志，返回对用户友好的 (标题, 描述) 元组。
    """
    if not error_msg:
        return "未知错误", "解析过程中发生未知错误。"

    # 清理掉换行，方便匹配
    clean_msg = " ".join(error_msg.splitlines())

    for err_def in YTDLP_ERRORS:
        for keyword in err_def.keywords:
            # 忽略大小写匹配
            if keyword.lower() in clean_msg.lower():
                detail = f"{err_def.description}\n\n建议操作：{err_def.action}"
                return err_def.title, detail

    # 兜底：未知错误，尽量提取 ERROR: 后面的内容
    match = re.search(r"ERROR:\s*(.*?)(?:\n|$)", error_msg, flags=re.IGNORECASE)
    if match:
        extracted = match.group(1).strip()
        # 限制长度
        if len(extracted) > 100:
            extracted = extracted[:97] + "..."
        return (
            "解析失败",
            f"系统遇到无法识别的错误：\n{extracted}\n\n建议尝试更新核心组件，或检查链接是否有效。",
        )

    # 如果连 ERROR 关键字都没找到，直接返回前 100 个字符
    fallback = error_msg.strip()
    if len(fallback) > 100:
        fallback = fallback[:97] + "..."
    return "解析或下载失败", f"原始信息：\n{fallback}"


def generate_issue_url(title: str, raw_error: str) -> str:
    """
    根据错误标题和原始日志，生成预填内容的 GitHub Issue 链接。
    """
    import urllib.parse

    # 限制原日志长度，防止 URL 过长导致浏览器拒绝 (通常 URL 限制在 2000-8000 字符)
    max_err_len = 1500
    if len(raw_error) > max_err_len:
        raw_error = raw_error[:max_err_len] + "\n...[Truncated]"

    issue_title = urllib.parse.quote(f"[AutoReport] {title}")

    body = (
        "### 错误描述\n"
        "自动捕获到的错误：\n"
        f"**{title}**\n\n"
        "### 错误日志\n"
        "```text\n"
        f"{raw_error}\n"
        "```\n\n"
        "### 其他信息\n"
        "- FluentYTDL 版本: \n"
        "- 操作系统: \n"
    )
    issue_body = urllib.parse.quote(body)

    # 附带 labels=bug
    return f"https://github.com/prideicker/FluentYTDL/issues/new?title={issue_title}&body={issue_body}&labels=bug"
