from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path


def _ensure_src_on_path() -> None:
    root_dir = Path(__file__).resolve().parents[1]
    src_dir = root_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


_ensure_src_on_path()

from fluentytdl.utils.translator import translate_error


@dataclass(frozen=True)
class Case:
    name: str
    raw: str
    must_contain_title: str


def run_case(case: Case) -> None:
    err = Exception(case.raw)
    out = translate_error(err)

    assert isinstance(out, dict), f"{case.name}: translate_error() should return dict"
    for key in ("title", "content", "suggestion", "raw_error"):
        assert key in out, f"{case.name}: missing key {key}"

    title = str(out.get("title") or "")
    assert case.must_contain_title in title, (
        f"{case.name}: title mismatch. expected to contain {case.must_contain_title!r}, got {title!r}"
    )


def main() -> None:
    # 注意：按需求，这里刻意不覆盖“链接无效/不受支持”分支。
    cases = [
        Case(
            name="403/风控",
            raw="ERROR: [youtube] ABC: Sign in to confirm you're not a bot (403)",
            must_contain_title="403",
        ),
        Case(
            name="需要登录",
            raw="ERROR: [youtube] ABC: This video is private. Sign in if you've been granted access.",
            must_contain_title="登录",
        ),
        Case(
            name="网络超时",
            raw="ERROR: timed out while trying to connect", 
            must_contain_title="网络",
        ),
        Case(
            name="连接失败",
            raw="ERROR: [generic] Unable to download webpage: <urlopen error [Errno 111] Connection refused>",
            must_contain_title="网络",
        ),
        Case(
            name="视频不可用",
            raw="ERROR: [youtube] ABC: Video unavailable", 
            must_contain_title="视频",
        ),
        Case(
            name="FFmpeg 缺失",
            raw="ERROR: Postprocessing: ffmpeg not found. Please install or provide the path.",
            must_contain_title="FFmpeg",
        ),
        Case(
            name="后处理失败",
            raw="ERROR: Postprocessing: Error during postprocessing", 
            must_contain_title="后处理",
        ),
    ]

    ok = 0
    for case in cases:
        try:
            run_case(case)
            print(f"OK  - {case.name}")
            ok += 1
        except Exception as e:
            print(f"FAIL- {case.name}: {e}")

    print(f"\n{ok}/{len(cases)} passed")

    # 输出一份样例结果，方便人工目检
    sample = translate_error(Exception(cases[0].raw))
    print("\nSample output:\n" + json.dumps(sample, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
