# FluentYTDL 版本管理最佳实践

## ✅ 当前状态

已完成版本管理体系搭建：

- ✅ 版本号已统一为 `1.0.19`
- ✅ 创建版本管理工具 `scripts/version_manager.py`
- ✅ 建立版本管理规范文档
- ✅ 添加 Git pre-commit hook（可选）

## 🎯 版本管理架构

```
FluentYTDL/
├── pyproject.toml                    # 主版本源（优先级最高）
├── src/fluentytdl/__init__.py        # Python 包版本
├── installer/FluentYTDL.iss          # 安装器版本
├── scripts/
│   └── version_manager.py            # 版本管理工具 ⭐
├── docs/
│   └── VERSION_MANAGEMENT.md         # 版本管理规范
└── githooks/
    └── pre-commit-version-check      # Git Hook（可选）
```

## 🚀 日常使用

### 场景 1: 检查版本状态

```bash
python scripts/version_manager.py check
```

### 场景 2: 发布新版本（Bug 修复）

```bash
# 1. 递增补丁版本
python scripts/version_manager.py bump patch

# 2. 提交并打标签
git add -A
git commit -m "chore: bump version to 1.0.20"
git tag v1.0.20
git push origin main --tags

# 3. 构建发布包
python scripts/build.py --target full
```

### 场景 3: 发布新功能

```bash
# 1. 递增次版本
python scripts/version_manager.py bump minor

# 2. 提交并打标签
git add -A
git commit -m "chore: bump version to 1.1.0"
git tag v1.1.0
git push origin main --tags

# 3. 构建发布包
python scripts/build.py --target full
```

### 场景 4: 手动设置版本

```bash
python scripts/version_manager.py set 1.2.0
git add -A
git commit -m "chore: bump version to 1.2.0"
git tag v1.2.0
git push origin main --tags
```

## 📊 版本号策略

| 变更类型 | 版本递增 | 命令 | 示例 |
|---------|---------|------|------|
| Bug 修复 | PATCH | `bump patch` | 1.0.19 → 1.0.20 |
| 新增功能 | MINOR | `bump minor` | 1.0.19 → 1.1.0 |
| 重大更新 | MAJOR | `bump major` | 1.0.19 → 2.0.0 |
| 预发布版 | 手动设置 | `set 1.1.0-beta.1` | 1.0.19 → 1.1.0-beta.1 |

## 🔧 工具命令速查

```bash
# 检查版本一致性
python scripts/version_manager.py check

# 查看版本摘要
python scripts/version_manager.py summary

# 设置新版本
python scripts/version_manager.py set <版本号>

# 自动递增
python scripts/version_manager.py bump [major|minor|patch]
```

## 🎨 Git 提交规范

### 版本更新提交

```bash
git commit -m "chore: bump version to <版本号>"
```

### 其他提交类型

```bash
feat:     新功能
fix:      Bug 修复
docs:     文档变更
style:    代码格式
refactor: 重构
perf:     性能优化
test:     测试
chore:    构建/工具变更
```

## ⚠️ 注意事项

### 1. 版本号同步

**问题**: 多个文件中的版本号不一致

**解决**: 
- 始终使用 `version_manager.py` 管理版本
- 提交前运行 `check` 命令
- 考虑启用 pre-commit hook

### 2. Git 标签管理

**最佳实践**:
- 标签格式: `v<版本号>` (如 `v1.0.19`)
- 使用附注标签: `git tag -a v1.0.19 -m "Release 1.0.19"`
- 及时推送标签: `git push origin --tags`

### 3. 预发布版本

**命名规范**:
- Alpha: `1.1.0-alpha.1`
- Beta: `1.1.0-beta.1`
- RC: `1.1.0-rc.1`

### 4. 构建系统集成

`scripts/build.py` 会自动从 `pyproject.toml` 读取版本号：

```python
def _get_version(self) -> str:
    """从 pyproject.toml 读取版本号"""
    pyproject = ROOT / "pyproject.toml"
    # 自动解析版本号...
```

## 📈 版本演进示例

```
1.0.0  → 初始发布
1.0.1  → Bug 修复
1.0.2  → Bug 修复
1.1.0  → 新功能：POT Provider 集成
1.1.1  → Bug 修复
1.2.0  → 新功能：批量下载
2.0.0  → 重大更新：架构重构
```

## 🔗 相关文档

- [完整版本管理规范](./VERSION_MANAGEMENT.md)
- [构建系统文档](./windows_build.md)
- [Git 工作流程](../CONTRIBUTING.md)

## 💡 快速启动清单

开始使用版本管理工具：

- [ ] 检查当前版本一致性: `python scripts/version_manager.py check`
- [ ] 如有不一致，运行: `python scripts/version_manager.py set 1.0.19`
- [ ] 阅读版本管理规范: `docs/VERSION_MANAGEMENT.md`
- [ ] 下次发布时使用 `bump` 命令递增版本
- [ ] 记得创建 Git 标签并推送

---

**版本管理工具创建**: 2026-02-05  
**当前项目版本**: 1.0.19  
**工具位置**: `scripts/version_manager.py`
