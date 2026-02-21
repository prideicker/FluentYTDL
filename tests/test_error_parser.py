import os
import sys

# Add src to pythonpath
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src"))
)

from fluentytdl.utils.translator import translate_error


class DummyError(Exception):
    pass


errors = [
    "ERROR: [youtube] aaaaaa: Sign in to confirm you're not a bot",
    "ERROR: [youtube] aaaaaa: Video unavailable in your country",
    "ERROR: [youtube] aaaaaa: Private video",
    "ERROR: ffprobe/ffmpeg not found",
]

for e in errors:
    print(f"--- Original: {e} ---")
    res = translate_error(DummyError(e))
    print(f"Title: {res['title']}")
    print(f"Content: {res['content']}")
    print(f"Suggestion: {res['suggestion']}")
    print()
