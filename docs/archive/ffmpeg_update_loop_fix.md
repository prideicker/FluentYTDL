# FFmpeg 组件更新无限循环问题分析与修复方案

> **文档创建日期**: 2026-02-20  
> **问题严重程度**: 🔴 严重  
> **涉及文件**: `src/fluentytdl/core/dependency_manager.py`, `src/fluentytdl/ui/settings_page.py`

---

## 1. 问题现象

用户成功更新 FFmpeg 后，再次检查更新时仍然提示"有新版本可用"，点击更新后问题反复出现，形成**无限更新循环**。

---

## 2. 根因分析

通过实际调试验证，发现存在 **3 个互相关联的缺陷**，共同导致了该问题。

### 缺陷 1（核心）：本地版本字符串与远程版本字符串格式根本不匹配

**本地版本检测逻辑**（`_get_local_version`，第 237-241 行）：

```python
# 执行 ffmpeg -version，解析输出的第一行
m = re.search(r"ffmpeg version ([^\s]+)", line)
```

实际捕获结果（BtbN 构建）：

```
ffmpeg version n7.1.3-40-gcddd06f3b9-20260219 Copyright (c) ...
                ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
捕获值 = "n7.1.3-40-gcddd06f3b9-20260219"
```

**远程版本检测逻辑**（`_get_remote_version`，第 348 行附近）：

```python
# 从 asset 文件名提取版本号
m = re.search(r"ffmpeg-n(\d+(?:\.\d+)*)", asset_name)
# asset_name = "ffmpeg-n7.1-latest-win64-gpl-7.1.zip"
# 捕获值 = "7.1"
```

**版本比较逻辑**（第 183-189 行）：

```python
c_norm = current_ver.lstrip("vn")   # "7.1.3-40-gcddd06f3b9-20260219"
l_norm = latest_ver.lstrip("vn")    # "7.1"

if c_norm != l_norm:                 # 永远为 True！
    update_available = True
```

**结论**：本地版本是完整构建字符串 `7.1.3-40-gcddd06f3b9-20260219`，远程版本仅为主版本号 `7.1`，两者在字符串级别**永远不可能相等**，导致更新始终被触发。

### 缺陷 2（加剧）：BtbN "latest" Release 是滚动构建

BtbN/FFmpeg-Builds 仓库的 `latest` release 特点：

| 字段 | 实际值 |
|---|---|
| `tag_name` | `"latest"`（固定不变） |
| `name` | `"Latest Auto-Build (2026-02-19 13:07)"` |
| asset 文件名 | `ffmpeg-n7.1-latest-win64-gpl-7.1.zip` |
| asset 内 ffmpeg 的实际版本 | `n7.1.3-40-gcddd06f3b9-20260219` |

- `tag_name` 永远是 `"latest"`，代码正确地尝试从 asset 文件名提取版本号
- 但 asset 文件名只包含**主版本号** `7.1`，而实际安装的二进制文件版本是 `n7.1.3-40-gcddd06f3b9-20260219`
- 这是一个**信息损失**问题：远程 API 根本无法提供与本地 `ffmpeg -version` 一致精度的版本号

### 缺陷 3（循环触发）：安装完成后自动重新检查

`settings_page.py` 第 278 行：

```python
def _on_install_finished(self, key):
    ...
    dependency_manager.check_update(self.component_key)  # 安装完后立刻检查
```

执行流程：
1. 用户点击"立即更新" → 下载并安装 ffmpeg
2. 安装完成 → 自动触发 `check_update`
3. 版本比较 → `"7.1.3-40-gcddd06f3b9-20260219" != "7.1"` → 显示"有更新"
4. 用户再次点击更新 → 回到步骤 1，**无限循环**

### 附加问题：find_asset 不区分多版本

BtbN 的 `latest` release 同时包含多个版本的构建：

```
ffmpeg-n7.1-latest-win64-gpl-7.1.zip   (7.1 分支)
ffmpeg-n8.0-latest-win64-gpl-8.0.zip   (8.0 分支)
ffmpeg-master-latest-win64-gpl.zip      (master 分支)
```

当前 `find_asset("ffmpeg-n")` 仅取第一个匹配项，并不保证是最新版本。

---

## 3. 修复方案

### 方案概述

采用**统一版本归一化 + 语义化版本比较**的策略，从根本上解决格式不一致问题。

### 修复 1：统一 FFmpeg 本地版本解析（核心修复）

**文件**: `dependency_manager.py` → `_get_local_version` 方法

将本地版本提取改为仅保留 `主版本号.次版本号`（或 `主.次.修订`），与远程格式一致：

```python
elif key == "ffmpeg":
    line = out.splitlines()[0]
    m = re.search(r"ffmpeg version ([^\s]+)", line)
    if m:
        raw = m.group(1)
        # 从完整版本字符串中提取核心版本号
        # 示例: "n7.1.3-40-gcddd06f3b9-20260219" → "7.1.3"
        # 示例: "6.1-essentials_build-www.gyan.dev" → "6.1"
        core = raw.lstrip("nN")
        # 取第一个非数字非点号前的部分作为核心版本
        vm = re.match(r"(\d+(?:\.\d+)*)", core)
        if vm:
            return vm.group(1)  # "7.1.3" 或 "6.1"
        return raw  # fallback
```

### 修复 2：改进远程版本提取，优先选择最高版本

**文件**: `dependency_manager.py` → `_get_remote_version` 的 ffmpeg 分支

```python
elif key == "ffmpeg":
    url = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/latest"
    resp = requests.get(url, proxies=proxies, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    # 收集所有版本化的 win64-gpl static 构建
    candidates = []
    for asset in data.get("assets", []):
        name = asset["name"]
        if "win64-gpl" in name and ".zip" in name and "shared" not in name:
            m = re.search(r"ffmpeg-n(\d+(?:\.\d+)*)", name)
            if m:
                ver_str = m.group(1)
                ver_tuple = tuple(int(x) for x in ver_str.split("."))
                candidates.append((ver_tuple, ver_str, asset["browser_download_url"], name))

    if candidates:
        # 按版本号降序排列，取最高版本
        candidates.sort(reverse=True, key=lambda x: x[0])
        _, tag, dl_url, asset_name = candidates[0]
    else:
        # Fallback: master 构建
        dl_url, asset_name, tag = "", "", "unknown"
        for asset in data.get("assets", []):
            if "win64-gpl" in asset["name"] and ".zip" in asset["name"] and "shared" not in asset["name"]:
                dl_url = asset["browser_download_url"]
                asset_name = asset["name"]
                tag = "master"
                break

    return tag, dl_url
```

### 修复 3：引入语义化版本比较

**文件**: `dependency_manager.py` → `UpdateCheckerWorker.run` 方法

替换简单的字符串不等式比较，改用语义化版本比较：

```python
def _normalize_version(self, ver: str) -> tuple[int, ...] | None:
    """将版本字符串归一化为可比较的元组。"""
    cleaned = ver.lstrip("vn").strip()
    m = re.match(r"(\d+(?:\.\d+)*)", cleaned)
    if m:
        return tuple(int(x) for x in m.group(1).split("."))
    return None

def run(self):
    try:
        exe_path = self.manager.get_exe_path(self.key)
        current_ver = self._get_local_version(self.key, exe_path)
        latest_ver, url = self._get_remote_version(self.key)

        update_available = False
        if latest_ver and latest_ver != "unknown":
            c_tuple = self._normalize_version(current_ver)
            l_tuple = self._normalize_version(latest_ver)

            if c_tuple is not None and l_tuple is not None:
                # 对齐元组长度进行比较 (7.1) vs (7.1.3) → (7.1.0) vs (7.1.3)
                max_len = max(len(c_tuple), len(l_tuple))
                c_padded = c_tuple + (0,) * (max_len - len(c_tuple))
                l_padded = l_tuple + (0,) * (max_len - len(l_tuple))
                # 仅当远程版本严格大于本地时才提示更新
                update_available = l_padded > c_padded
            else:
                # 无法解析则 fallback 到字符串比较
                c_norm = current_ver.lstrip("vn")
                l_norm = latest_ver.lstrip("vn")
                update_available = c_norm != l_norm

        result = {
            "current": current_ver,
            "latest": latest_ver,
            "update_available": update_available,
            "url": url
        }
        self.finished_signal.emit(self.key, result)
    except Exception as e:
        logger.error(f"Update check failed for {self.key}: {e}")
        self.error_signal.emit(self.key, str(e))
```

**关键改进**：只有当远程版本**严格大于**本地版本时才提示更新。这解决了：
- `7.1.3`（本地）vs `7.1`（远程）→ `(7,1,3) > (7,1,0)` → 本地更新，**不提示更新** ✅
- `7.1`（本地）vs `8.0`（远程）→ `(8,0) > (7,1)` → **提示更新** ✅
- `8.0`（本地）vs `8.0`（远程）→ 相等 → **不提示更新** ✅

### 修复 4：安装后抑制误报（防御性）

即使版本比较修复后，仍建议在安装完成后的重新检查中增加一个短暂冷却标记，避免边界情况：

```python
# 在 DependencyManager 中添加
def __init__(self):
    super().__init__()
    self._workers = {}
    self._just_installed: set[str] = set()  # 记录刚刚安装完的组件
    ...

def _on_install_finished(self, key):
    self._just_installed.add(key)
    self.install_finished.emit(key)
    self._workers.pop(f"install_{key}", None)

def _on_check_finished(self, key, result):
    # 如果是刚安装完的组件，且版本比较仍显示有更新，抑制误报
    if key in self._just_installed:
        self._just_installed.discard(key)
        if result.get('update_available') and result.get('current') != 'unknown':
            logger.info(f"Suppressing update notification for {key} (just installed)")
            result['update_available'] = False
    
    if key in self.components:
        self.components[key].current_version = result.get('current')
        self.components[key].latest_version = result.get('latest')
        self.components[key].download_url = result.get('url')
    self.check_finished.emit(key, result)
    self._workers.pop(f"check_{key}", None)
```

---

## 4. 修复验证矩阵

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 本地 `7.1.3`，远程 `7.1` | ❌ 提示更新 | ✅ 不提示 |
| 本地 `7.1`，远程 `8.0` | ✅ 提示更新 | ✅ 提示更新 |
| 本地 `8.0`，远程 `8.0` | ✅ 不提示 | ✅ 不提示 |
| 本地 `n7.1.3-40-gcddd06f3b9`，远程 `7.1` | ❌ 提示更新 | ✅ 不提示 |
| 安装完成后自动检查 | ❌ 立刻再次提示更新 | ✅ 正确显示"已是最新" |
| BtbN 同时有 n7.1 和 n8.0 | ⚠️ 随机取第一个 | ✅ 取最高版本 n8.0 |

---

## 5. 实施优先级

| 优先级 | 修复项 | 工作量 |
|---|---|---|
| P0 | 修复 1 + 修复 3（版本解析与比较） | 小（约 30 行改动） |
| P0 | 修复 2（远程版本选择最高版本） | 小（约 15 行改动） |
| P1 | 修复 4（安装后抑制误报） | 小（约 10 行改动） |

建议一次性全部实施，总改动量约 55 行代码。

---

## 6. 影响范围

- **仅影响 FFmpeg 组件**：其他组件（yt-dlp、deno、pot-provider 等）使用语义化版本号且本地/远程格式一致，不受此问题影响。但修复 3 的语义化比较逻辑会使所有组件的版本比较更健壮。
- **无破坏性变更**：修复仅改进内部版本解析和比较逻辑，不影响 UI 界面和用户操作流程。
