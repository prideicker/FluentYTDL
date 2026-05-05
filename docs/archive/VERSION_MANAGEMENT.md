# FluentYTDL 版本管理规范

## 📋 概述

本文档定义 FluentYTDL 项目的版本管理规范和工作流程。

## 🎯 版本号格式

采用 **语义化版本（Semantic Versioning）** 规范：`MAJOR.MINOR.PATCH`

- **MAJOR（主版本号）**: 重大架构变更，可能不向后兼容
- **MINOR（次版本号）**: 新增功能，向后兼容
- **PATCH（补丁版本号）**: Bug 修复，向后兼容

示例：
- `1.0.0` - 首个正式版
- `1.1.0` - 新增功能
- `1.1.1` - Bug 修复
- `2.0.0` - 重大更新

## 📁 版本文件位置

版本号需要在以下文件中保持一致：

| 文件 | 位置 | 格式 | 用途 |
|------|------|------|------|
| `pyproject.toml` | 根目录 | `version = "1.0.19"` | Python 项目配置 |
| `__init__.py` | `src/fluentytdl/` | `__version__ = "1.0.19"` | Python 包版本 |
| `FluentYTDL.iss` | `installer/` | `#define MyAppVersion "1.0.19"` | Windows 安装器 |

## 🛠️ 版本管理工具

使用 `scripts/version_manager.py` 统一管理版本号。

### 检查版本一致性

```bash
python scripts/version_manager.py check
```

**输出示例：**
```
🔍 检查版本号一致性...

  ✅ 项目配置文件    : 1.0.19     (pyproject.toml)
  ✅ Python 包版本   : 1.0.19     (__init__.py)
  ✅ Inno Setup 默认版本: 1.0.19  (FluentYTDL.iss)

✅ 所有版本号一致: 1.0.19
```

### 设置新版本号

```bash
# 手动指定版本号
python scripts/version_manager.py set 1.0.20
```

### 自动递增版本号

```bash
# 补丁版本递增 (1.0.19 → 1.0.20)
python scripts/version_manager.py bump patch

# 次版本递增 (1.0.19 → 1.1.0)
python scripts/version_manager.py bump minor

# 主版本递增 (1.0.19 → 2.0.0)
python scripts/version_manager.py bump major
```

### 查看版本摘要

```bash
python scripts/version_manager.py summary
```

## 📝 发布流程

### 1. 准备发布

```bash
# 1. 确保工作区干净
git status

# 2. 拉取最新代码
git pull origin main

# 3. 运行测试（如有）
pytest

# 4. 检查版本一致性
python scripts/version_manager.py check
```

### 2. 更新版本号

根据变更类型选择合适的版本递增：

```bash
# Bug 修复 → patch
python scripts/version_manager.py bump patch

# 新功能 → minor
python scripts/version_manager.py bump minor

# 重大更新 → major
python scripts/version_manager.py bump major
```

或手动设置：

```bash
python scripts/version_manager.py set 1.1.0
```

### 3. 提交版本更改

```bash
# 添加所有更改
git add -A

# 提交（使用规范化的提交信息）
git commit -m "chore: bump version to 1.0.20"

# 创建版本标签
git tag v1.0.20

# 推送到远程（包括标签）
git push origin main
git push origin v1.0.20
```

### 4. 构建和发布

```bash
# 构建完整包（包含安装器和便携版）
python scripts/build.py --target full

# 发布到 GitHub Releases
# （上传 release/ 目录中的文件）
```

## 🏷️ Git 标签规范

### 标签命名

- 版本标签：`v1.0.19`（必须以 `v` 开头）
- 预发布版本：`v1.1.0-beta.1`, `v2.0.0-rc.1`

### 创建标签

```bash
# 轻量标签（不推荐）
git tag v1.0.20

# 附注标签（推荐）
git tag -a v1.0.20 -m "Release version 1.0.20"

# 推送标签到远程
git push origin v1.0.20

# 推送所有标签
git push origin --tags
```

### 删除标签

```bash
# 删除本地标签
git tag -d v1.0.20

# 删除远程标签
git push origin :refs/tags/v1.0.20
```

## 📊 版本历史追踪

### 查看版本标签

```bash
# 列出所有标签
git tag

# 列出特定模式的标签
git tag -l "v1.0.*"

# 显示标签详情
git show v1.0.19
```

### 版本差异对比

```bash
# 对比两个版本的变更
git diff v1.0.18..v1.0.19

# 查看版本之间的提交日志
git log v1.0.18..v1.0.19 --oneline
```

## 🔄 版本回退

如果需要回退到旧版本：

```bash
# 1. 回退版本号
python scripts/version_manager.py set 1.0.18

# 2. 提交回退
git add -A
git commit -m "chore: revert version to 1.0.18"

# 3. 删除错误的标签（如有）
git tag -d v1.0.19
git push origin :refs/tags/v1.0.19
```

## 📋 提交信息规范

使用 Conventional Commits 规范：

```
<type>: <subject>

<body>

<footer>
```

### 类型（type）

- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档变更
- `style`: 代码格式（不影响代码运行）
- `refactor`: 重构（既不是新增功能，也不是修复 bug）
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建过程或辅助工具的变动
- `build`: 构建系统或外部依赖变更

### 示例

```bash
# 版本更新
git commit -m "chore: bump version to 1.0.20"

# 新功能
git commit -m "feat: add POT Provider integration"

# Bug 修复
git commit -m "fix: resolve format selector display issue"

# 文档
git commit -m "docs: update version management guide"
```

## 🚨 常见问题

### Q: 版本号不一致怎么办？

**A:** 运行版本检查和修复：

```bash
python scripts/version_manager.py check
python scripts/version_manager.py set <目标版本>
```

### Q: 忘记创建 Git 标签怎么办？

**A:** 找到对应的提交并补打标签：

```bash
# 查找提交
git log --oneline

# 在特定提交上打标签
git tag v1.0.19 <commit-hash>
git push origin v1.0.19
```

### Q: 如何查看当前版本？

**A:** 多种方式：

```bash
# 使用版本管理工具
python scripts/version_manager.py summary

# 查看 pyproject.toml
grep "version" pyproject.toml

# 在 Python 中
python -c "from fluentytdl import __version__; print(__version__)"

# 查看最新 Git 标签
git describe --tags --abbrev=0
```

### Q: 预发布版本如何管理？

**A:** 使用后缀标识：

```bash
# Beta 版本
python scripts/version_manager.py set 1.1.0-beta.1

# Release Candidate
python scripts/version_manager.py set 2.0.0-rc.1

# Alpha 版本
python scripts/version_manager.py set 1.2.0-alpha.1
```

## 🔗 相关资源

- [语义化版本规范](https://semver.org/lang/zh-CN/)
- [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)
- [Git 标签文档](https://git-scm.com/book/zh/v2/Git-基础-打标签)

## 📅 更新日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-02-05 | 1.0.0 | 初始版本管理规范 |
