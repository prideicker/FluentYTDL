# 开发者文档（摘要）

## 项目结构（简要）
- `src/fluentytdl/`：应用源码（UI、core、utils）。
- `scripts/`：辅助脚本（maintenance、icon install、history hints）。
- `package.ps1`：Windows 打包脚本（根目录入口，调用 `scripts/build.ps1`）。

## 关键改动记录
- 删除策略：引入统一 `deletion_policy`（KeepFiles / DeleteFiles / AlwaysAsk），替换原来的多个布尔开关。
- Worker：改进子进程 stdout 读取为二进制并逐步尝试 `utf-8`/`gbk` 解码，增强对路径收集与错误回退的处理。
- UI 组件：新增 `ValidatedEditDialog` 与 `SmartSettingCard` 用于弹窗编辑敏感设置；更新设置页分组（高级/自动化/行为）。
- 程序稳定性：修复 tray icon 与字体警告，删除流程在删除前先安全停止 worker（使用 `stop()`/`hasattr` 保护）。

## 本地开发
- 安装依赖：`python -m pip install -r requirements-dev.txt`。
- 运行测试：`pytest -q`。
- 运行类型检查：`pyright`。

## 运行与调试
- 运行主程序：`python main.py`。
- 打包（Windows）：在 PowerShell 中运行 `package.ps1`（或直接运行 `scripts\build.ps1 -Flavor full`）。

## 维护与清理
- `scripts/maintenance.py` 提供 dry-run（默认）和 `--force` 真删模式。请始终先 dry-run。

## 发布与历史操作
- 发布流程由维护者统一管理；如需发布或移除敏感历史，请联系维护者以便安排安全处理。

## 贡献指南快速提示
- 代码风格：保持现有代码风格，运行 `ruff`/`pyright` 检查。
- 提交：小而明确的提交，CI 会运行基本检查与测试。

---
需要我为 README、CONTRIBUTING 或更详细的架构文档生成初稿并提交到仓库吗？
