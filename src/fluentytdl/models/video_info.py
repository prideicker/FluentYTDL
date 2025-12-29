"""Typed video metadata models (reserved for Stage 2/3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class VideoInfo:
    url: str
    title: str | None = None
