from PySide6.QtWidgets import QWidget
from qfluentwidgets import InfoBar, InfoBarPosition


def do_relogin(parent_widget: QWidget) -> None:
    """处理重登录（例如打开 DLE 登录对话框）"""
    # 尝试寻找主窗口并调用其 switch_to_settings 或类似方法
    main_win = parent_widget.window()
    settings_iface = getattr(main_win, "settings_interface", None)
    if settings_iface is not None:
        if hasattr(main_win, "switchTo"):
            main_win.switchTo(settings_iface)  # type: ignore
        InfoBar.info(
            "提示",
            "请在设置页中重新提取或验证您的账号 Cookie。",
            parent=main_win,
            position=InfoBarPosition.TOP,
            duration=5000,
        )
    else:
        InfoBar.warning(
            "不支持的操作",
            "无法定位到设置界面。",
            parent=main_win,
            position=InfoBarPosition.TOP,
            duration=3000,
        )


def extract_cookie(parent_widget: QWidget) -> None:
    """提取 Cookie 修复动作"""
    do_relogin(parent_widget)


def switch_proxy(parent_widget: QWidget) -> None:
    """切换代理修复动作"""
    main_win = parent_widget.window()
    settings_iface = getattr(main_win, "settings_interface", None)
    if settings_iface is not None and hasattr(main_win, "switchTo"):
        main_win.switchTo(settings_iface)  # type: ignore
        InfoBar.info(
            "网络设置",
            "请在此配置可用的代理节点。",
            parent=main_win,
            position=InfoBarPosition.TOP,
            duration=5000,
        )


def change_download_dir(parent_widget: QWidget) -> None:
    """更改下载目录"""
    main_win = parent_widget.window()
    settings_iface = getattr(main_win, "settings_interface", None)
    if settings_iface is not None and hasattr(main_win, "switchTo"):
        main_win.switchTo(settings_iface)  # type: ignore
        InfoBar.info(
            "存储设置",
            "请更改默认的下载保存路径。",
            parent=main_win,
            position=InfoBarPosition.TOP,
            duration=5000,
        )


FIX_ACTIONS = {
    "relogin": do_relogin,
    "extract_cookie": extract_cookie,
    "switch_proxy": switch_proxy,
    "change_download_dir": change_download_dir,
}


def execute_fix_action(action_id: str, parent_widget: QWidget) -> bool:
    """执行修复动作"""
    action_func = FIX_ACTIONS.get(action_id)
    if action_func:
        try:
            action_func(parent_widget)
            return True
        except Exception as e:
            InfoBar.error(
                "执行失败",
                f"尝试执行自动修复时发生错误: {e}",
                parent=parent_widget.window(),
                position=InfoBarPosition.TOP,
            )
            return False
    return False
