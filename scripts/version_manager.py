#!/usr/bin/env python3
"""
FluentYTDL 版本管理工具

统一管理所有文件中的版本号，支持三种版本前缀：
  v-X.Y.Z    — 正式发布（稳定版），GitHub Release Latest
  pre-X.Y.Z  — 预发布（候选版），GitHub Release Pre-release
  beta-X.Y.Z — 测试版，仅项目负责人在群/频道分发

VERSION 文件（根目录）是唯一的 source of truth。
pyproject.toml 和 Inno Setup 只存储纯数字版本（PEP 440 / Inno Setup 兼容）。

用法:
    python scripts/version_manager.py check              # 检查版本一致性
    python scripts/version_manager.py set v-3.0.18       # 设置新版本
    python scripts/version_manager.py set pre-3.0.18     # 设置预发布版本
    python scripts/version_manager.py set beta-0.0.5     # 设置测试版本
    python scripts/version_manager.py bump major|minor|patch  # 自动递增版本
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class VersionFile:
    """版本文件配置"""

    path: Path
    pattern: str  # 正则表达式模式，必须包含一个捕获组
    template: str  # 替换模板，使用 {version} 占位符
    description: str
    writes_full: bool = False  # True: 写入完整带前缀版本; False: 只写纯数字


def _parse_prefix(version_str: str) -> tuple[str, str]:
    """解析版本前缀和数字部分。

    "v-3.0.18"    → ("v-", "3.0.18")
    "pre-3.0.18"  → ("pre-", "3.0.18")
    "beta-0.0.5"  → ("beta-", "0.0.5")
    "3.0.18"      → ("v-", "3.0.18")  # 无前缀默认 v-
    """
    for pfx in ("v-", "pre-", "beta-"):
        if version_str.startswith(pfx):
            return pfx, version_str[len(pfx):]
    return "v-", version_str


class VersionManager:
    """版本管理器"""

    VERSION_FILES = [
        VersionFile(
            path=ROOT / "VERSION",
            pattern=r"^.+$",
            template="{version}",
            description="VERSION 源文件",
            writes_full=True,
        ),
        VersionFile(
            path=ROOT / "pyproject.toml",
            pattern=r'^version\s*=\s*["\']([^"\']+)["\']',
            template='version = "{version}"',
            description="项目配置文件",
            writes_full=False,
        ),
        VersionFile(
            path=ROOT / "src" / "fluentytdl" / "__init__.py",
            pattern=r'^__version__\s*=\s*["\']([^"\']+)["\']',
            template='__version__ = "{version}"',
            description="Python 包版本",
            writes_full=True,
        ),
        VersionFile(
            path=ROOT / "installer" / "FluentYTDL.iss",
            pattern=r'#define\s+MyAppVersion\s+"([^"]+)"',
            template='#define MyAppVersion "{version}"',
            description="Inno Setup 默认版本",
            writes_full=False,
        ),
    ]

    def __init__(self):
        self.current_versions: dict[Path, str] = {}

    def _read_version_from_file(self, vf: VersionFile) -> str | None:
        """从文件中读取版本号。返回 None 表示文件不存在或无法读取。"""
        if not vf.path.exists():
            return None

        # VERSION 文件特殊处理：纯文本单行
        if vf.path.name == "VERSION":
            return vf.path.read_text(encoding="utf-8").strip()

        content = vf.path.read_text(encoding="utf-8")

        # __init__.py 特殊处理：动态读取 VERSION 文件时返回 VERSION 的值
        if vf.path.name == "__init__.py" and "_read_version()" in content:
            version_vf = self.VERSION_FILES[0]
            return self._read_version_from_file(version_vf)

        match = re.search(vf.pattern, content, re.MULTILINE)
        return match.group(1) if match else None

    def check_consistency(self) -> bool:
        """检查版本一致性。

        VERSION 和 __init__.py 应存储完整版本（含前缀），
        pyproject.toml 和 .iss 应存储纯数字版本。
        """
        print("🔍 检查版本号一致性...\n")

        self.current_versions = {}

        # 读取 VERSION 文件获取期望值
        version_vf = self.VERSION_FILES[0]  # VERSION
        full_version = self._read_version_from_file(version_vf)
        if not full_version:
            print("  ❌ VERSION 文件不存在或为空")
            return False

        prefix, numeric = _parse_prefix(full_version)
        print(f"  📌 VERSION 源文件: {full_version} (前缀: {prefix}, 数字: {numeric})\n")

        all_ok = True
        for vf in self.VERSION_FILES:
            actual = self._read_version_from_file(vf)
            if actual is None:
                print(f"  ⚠️  {vf.description}: 文件不存在 - {vf.path}")
                continue

            self.current_versions[vf.path] = actual

            # 判断期望值
            expected = full_version if vf.writes_full else numeric
            if actual == expected:
                print(f"  ✅ {vf.description:20s}: {actual}")
            else:
                print(f"  ❌ {vf.description:20s}: {actual} (期望: {expected})")
                all_ok = False

        print()
        if all_ok:
            print(f"✅ 所有版本号一致: {full_version}")
        else:
            print("❌ 版本号不一致")
        return all_ok

    def get_current_version(self) -> str | None:
        """获取当前完整版本（从 VERSION 文件）"""
        vf = self.VERSION_FILES[0]
        return self._read_version_from_file(vf)

    def set_version(self, new_version: str) -> bool:
        """设置新版本号到所有文件。

        new_version 格式: "v-3.0.18" / "pre-3.0.18" / "beta-0.0.5"
        无前缀时默认添加 "v-" 前缀。
        """
        # 确保有前缀
        if not any(new_version.startswith(p) for p in ("v-", "pre-", "beta-")):
            new_version = f"v-{new_version}"

        # 验证数字部分格式
        prefix, numeric = _parse_prefix(new_version)
        if not self._is_valid_numeric_version(numeric):
            print(f"❌ 无效的版本号格式: {new_version}")
            print("   数字部分应符合语义化版本规范，如: 1.0.0, 1.2.3, 2.0.0")
            return False

        print(f"📝 设置版本号为: {new_version}")
        print(f"   前缀: {prefix}, 数字: {numeric}\n")

        success_count = 0
        for vf in self.VERSION_FILES:
            if not vf.path.exists():
                print(f"  ⚠️  跳过 {vf.description}: 文件不存在")
                continue

            # __init__.py 使用动态读取时跳过（运行时自动从 VERSION 读取）
            if vf.path.name == "__init__.py":
                content_check = vf.path.read_text(encoding="utf-8")
                if "_read_version()" in content_check:
                    print(f"  ⏭️  {vf.description:20s}: 动态读取，无需写入")
                    success_count += 1
                    continue

            try:
                content_to_write = new_version if vf.writes_full else numeric
                old_version = self._read_version_from_file(vf)

                if vf.path.name == "VERSION":
                    # VERSION 文件：纯文本写入
                    vf.path.write_text(content_to_write + "\n", encoding="utf-8")
                else:
                    # 其他文件：正则替换
                    content = vf.path.read_text(encoding="utf-8")
                    new_line = vf.template.format(version=content_to_write)
                    content = re.sub(vf.pattern, new_line, content, flags=re.MULTILINE)
                    vf.path.write_text(content, encoding="utf-8")

                status = (
                    f"{old_version} → {content_to_write}"
                    if old_version
                    else f"设置为 {content_to_write}"
                )
                print(f"  ✅ {vf.description:20s}: {status}")
                success_count += 1

            except Exception as e:
                print(f"  ❌ {vf.description:20s}: 失败 - {e}")

        print(f"\n✅ 已更新 {success_count}/{len(self.VERSION_FILES)} 个文件")
        return success_count == len(
            [vf for vf in self.VERSION_FILES if vf.path.exists()]
        )

    def bump_version(self, bump_type: Literal["major", "minor", "patch"]) -> bool:
        """自动递增版本号（保留当前前缀）"""
        current = self.get_current_version()
        if not current:
            print("❌ 无法获取当前版本号")
            return False

        prefix, numeric = _parse_prefix(current)
        parts = numeric.split(".")
        if len(parts) < 3:
            print(f"❌ 版本号格式不正确: {numeric}")
            return False

        try:
            major = int(parts[0])
            minor = int(parts[1])
            patch_str = parts[2].split("-")[0]
            patch = int(patch_str)
        except ValueError:
            print(f"❌ 无法解析版本号: {numeric}")
            return False

        if bump_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump_type == "minor":
            minor += 1
            patch = 0
        elif bump_type == "patch":
            patch += 1

        new_numeric = f"{major}.{minor}.{patch}"
        new_version = f"{prefix}{new_numeric}"

        print(f"🔼 版本递增: {current} → {new_version} ({bump_type})\n")
        return self.set_version(new_version)

    @staticmethod
    def _is_valid_numeric_version(version: str) -> bool:
        """验证纯数字版本号格式（语义化版本）"""
        pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.-]+))?(?:\+([a-zA-Z0-9.-]+))?$"
        return re.match(pattern, version) is not None

    def generate_summary(self) -> None:
        """生成版本信息摘要"""
        current = self.get_current_version()
        if not current:
            print("❌ 无法获取当前版本号")
            return

        prefix, numeric = _parse_prefix(current)
        prefix_name = {"v-": "正式版", "pre-": "预发布", "beta-": "测试版"}.get(
            prefix, "未知"
        )

        print("=" * 60)
        print("FluentYTDL 版本信息")
        print("=" * 60)
        print(f"当前版本: {current}")
        print(f"  类型: {prefix_name} (前缀: {prefix})")
        print(f"  数字: {numeric}")
        print()
        print("版本文件:")
        for vf in self.VERSION_FILES:
            status = "✓" if vf.path.exists() else "✗"
            kind = "完整" if vf.writes_full else "纯数字"
            print(
                f"  [{status}] {vf.description:20s}: {kind:4s} ({vf.path.relative_to(ROOT)})"
            )
        print()
        print("版本前缀规范:")
        print("  v-    正式发布 → GitHub Release (Latest)")
        print("  pre-  预发布   → GitHub Release (Pre-release)")
        print("  beta- 测试版   → 仅 Artifacts + 群/频道分发")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="FluentYTDL 版本管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/version_manager.py check              # 检查版本一致性
  python scripts/version_manager.py set v-3.0.18       # 设置正式版
  python scripts/version_manager.py set pre-3.0.18     # 设置预发布版
  python scripts/version_manager.py set beta-0.0.5     # 设置测试版
  python scripts/version_manager.py bump patch         # 递增补丁版本 (保留前缀)
  python scripts/version_manager.py bump minor         # 递增次版本
  python scripts/version_manager.py bump major         # 递增主版本
  python scripts/version_manager.py summary            # 显示版本摘要
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    subparsers.add_parser("check", help="检查版本号一致性")

    set_parser = subparsers.add_parser("set", help="设置新版本号")
    set_parser.add_argument(
        "version",
        help="新版本号，如: v-3.0.18, pre-3.0.18, beta-0.0.5 (无前缀默认 v-)",
    )

    bump_parser = subparsers.add_parser("bump", help="自动递增版本号")
    bump_parser.add_argument(
        "type",
        choices=["major", "minor", "patch"],
        help="递增类型: major (主版本), minor (次版本), patch (补丁版本)",
    )

    subparsers.add_parser("summary", help="显示版本信息摘要")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    manager = VersionManager()

    if args.command == "check":
        success = manager.check_consistency()
        return 0 if success else 1

    elif args.command == "set":
        success = manager.set_version(args.version)
        if success:
            print("\n💡 提示: 记得提交版本更改到 Git:")
            print("   git add -A")
            print(f'   git commit -m "release: {args.version}"')
            print(f"   git tag {args.version}")
        return 0 if success else 1

    elif args.command == "bump":
        success = manager.bump_version(args.type)
        if success:
            new_version = manager.get_current_version()
            print("\n💡 提示: 记得提交版本更改到 Git:")
            print("   git add -A")
            print(f'   git commit -m "release: {new_version}"')
            print(f"   git tag {new_version}")
        return 0 if success else 1

    elif args.command == "summary":
        manager.generate_summary()
        return 0

    return 0


if __name__ == "__main__":
    import io
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
