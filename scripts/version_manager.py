#!/usr/bin/env python3
"""
FluentYTDL 版本管理工具

功能：
- 统一管理所有文件中的版本号
- 自动同步版本号到各个配置文件
- 生成版本变更日志
- 支持语义化版本（Semantic Versioning）

用法:
    python scripts/version_manager.py check              # 检查版本一致性
    python scripts/version_manager.py set 1.0.20         # 设置新版本
    python scripts/version_manager.py bump major|minor|patch  # 自动递增版本
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
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


class VersionManager:
    """版本管理器"""

    # 所有需要同步版本号的文件
    VERSION_FILES = [
        VersionFile(
            path=ROOT / "pyproject.toml",
            pattern=r'^version\s*=\s*["\']([^"\']+)["\']',
            template='version = "{version}"',
            description="项目配置文件",
        ),
        VersionFile(
            path=ROOT / "src" / "fluentytdl" / "__init__.py",
            pattern=r'^__version__\s*=\s*["\']([^"\']+)["\']',
            template='__version__ = "{version}"',
            description="Python 包版本",
        ),
        VersionFile(
            path=ROOT / "installer" / "FluentYTDL.iss",
            pattern=r'#define\s+MyAppVersion\s+"([^"]+)"',
            template='#define MyAppVersion "{version}"',
            description="Inno Setup 默认版本",
        ),
    ]

    def __init__(self):
        self.current_versions: dict[Path, str] = {}

    def check_consistency(self) -> bool:
        """检查版本一致性"""
        print("🔍 检查版本号一致性...\n")

        self.current_versions = {}
        all_versions = set()

        for vf in self.VERSION_FILES:
            if not vf.path.exists():
                print(f"  ⚠️  {vf.description}: 文件不存在 - {vf.path}")
                continue

            content = vf.path.read_text(encoding="utf-8")
            match = re.search(vf.pattern, content, re.MULTILINE)

            if match:
                version = match.group(1)
                self.current_versions[vf.path] = version
                all_versions.add(version)
                status = "✅" if len(all_versions) == 1 else "❌"
                print(f"  {status} {vf.description:20s}: {version:10s} ({vf.path.name})")
            else:
                print(f"  ❌ {vf.description:20s}: 未找到版本号模式")

        print()

        if len(all_versions) == 0:
            print("❌ 未找到任何版本号")
            return False
        elif len(all_versions) == 1:
            version = list(all_versions)[0]
            print(f"✅ 所有版本号一致: {version}")
            return True
        else:
            print(f"❌ 版本号不一致，发现 {len(all_versions)} 个不同版本:")
            for v in sorted(all_versions):
                files = [
                    vf.description
                    for vf in self.VERSION_FILES
                    if self.current_versions.get(vf.path) == v
                ]
                print(f"   - {v}: {', '.join(files)}")
            return False

    def get_current_version(self) -> str | None:
        """获取当前版本（从 pyproject.toml）"""
        pyproject = ROOT / "pyproject.toml"
        if not pyproject.exists():
            return None

        content = pyproject.read_text(encoding="utf-8")
        match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
        return match.group(1) if match else None

    def set_version(self, new_version: str) -> bool:
        """设置新版本号到所有文件"""
        # 验证版本号格式
        if not self._is_valid_version(new_version):
            print(f"❌ 无效的版本号格式: {new_version}")
            print("   版本号应符合语义化版本规范，如: 1.0.0, 1.2.3, 2.0.0-beta.1")
            return False

        print(f"📝 设置版本号为: {new_version}\n")

        success_count = 0
        for vf in self.VERSION_FILES:
            if not vf.path.exists():
                print(f"  ⚠️  跳过 {vf.description}: 文件不存在")
                continue

            try:
                content = vf.path.read_text(encoding="utf-8")
                old_version = None

                # 查找旧版本
                match = re.search(vf.pattern, content, re.MULTILINE)
                if match:
                    old_version = match.group(1)

                # 替换版本号
                new_line = vf.template.format(version=new_version)
                new_content = re.sub(vf.pattern, new_line, content, flags=re.MULTILINE)

                # 写入文件
                vf.path.write_text(new_content, encoding="utf-8")

                status = (
                    f"{old_version} → {new_version}" if old_version else f"设置为 {new_version}"
                )
                print(f"  ✅ {vf.description:20s}: {status}")
                success_count += 1

            except Exception as e:
                print(f"  ❌ {vf.description:20s}: 失败 - {e}")

        print(f"\n✅ 已更新 {success_count}/{len(self.VERSION_FILES)} 个文件")
        return success_count == len([vf for vf in self.VERSION_FILES if vf.path.exists()])

    def bump_version(self, bump_type: Literal["major", "minor", "patch"]) -> bool:
        """自动递增版本号"""
        current = self.get_current_version()
        if not current:
            print("❌ 无法获取当前版本号")
            return False

        # 解析当前版本
        parts = current.split(".")
        if len(parts) < 3:
            print(f"❌ 版本号格式不正确: {current}")
            return False

        try:
            major = int(parts[0])
            minor = int(parts[1])
            # 处理 patch 可能包含后缀的情况（如 1.0.0-beta）
            patch_str = parts[2].split("-")[0]
            patch = int(patch_str)
        except ValueError:
            print(f"❌ 无法解析版本号: {current}")
            return False

        # 递增版本号
        if bump_type == "major":
            major += 1
            minor = 0
            patch = 0
        elif bump_type == "minor":
            minor += 1
            patch = 0
        elif bump_type == "patch":
            patch += 1

        new_version = f"{major}.{minor}.{patch}"

        print(f"🔼 版本递增: {current} → {new_version} ({bump_type})\n")
        return self.set_version(new_version)

    @staticmethod
    def _is_valid_version(version: str) -> bool:
        """验证版本号格式（语义化版本）"""
        # 基础格式: X.Y.Z 或 X.Y.Z-prerelease+build
        pattern = r"^(\d+)\.(\d+)\.(\d+)(?:-([a-zA-Z0-9.-]+))?(?:\+([a-zA-Z0-9.-]+))?$"
        return re.match(pattern, version) is not None

    def generate_summary(self) -> None:
        """生成版本信息摘要"""
        current = self.get_current_version()
        if not current:
            print("❌ 无法获取当前版本号")
            return

        print("=" * 60)
        print("FluentYTDL 版本信息")
        print("=" * 60)
        print(f"当前版本: {current}")
        print()
        print("版本文件:")
        for vf in self.VERSION_FILES:
            status = "✓" if vf.path.exists() else "✗"
            print(f"  [{status}] {vf.description:20s}: {vf.path.relative_to(ROOT)}")
        print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="FluentYTDL 版本管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/version_manager.py check              # 检查版本一致性
  python scripts/version_manager.py set 1.0.20         # 设置新版本号
  python scripts/version_manager.py bump patch         # 递增补丁版本 (1.0.19 → 1.0.20)
  python scripts/version_manager.py bump minor         # 递增次版本 (1.0.19 → 1.1.0)
  python scripts/version_manager.py bump major         # 递增主版本 (1.0.19 → 2.0.0)
  python scripts/version_manager.py summary            # 显示版本摘要
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="命令")

    # check 命令
    subparsers.add_parser("check", help="检查版本号一致性")

    # set 命令
    set_parser = subparsers.add_parser("set", help="设置新版本号")
    set_parser.add_argument("version", help="新版本号 (如: 1.0.20)")

    # bump 命令
    bump_parser = subparsers.add_parser("bump", help="自动递增版本号")
    bump_parser.add_argument(
        "type",
        choices=["major", "minor", "patch"],
        help="递增类型: major (主版本), minor (次版本), patch (补丁版本)",
    )

    # summary 命令
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
            print(f'   git commit -m "chore: bump version to {args.version}"')
            print(f"   git tag v{args.version}")
        return 0 if success else 1

    elif args.command == "bump":
        success = manager.bump_version(args.type)
        if success:
            new_version = manager.get_current_version()
            print("\n💡 提示: 记得提交版本更改到 Git:")
            print("   git add -A")
            print(f'   git commit -m "chore: bump version to {new_version}"')
            print(f"   git tag v{new_version}")
        return 0 if success else 1

    elif args.command == "summary":
        manager.generate_summary()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
