import sys
from pathlib import Path
# ensure project root on sys.path for direct script run
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from fluentytdl.utils.paths import locate_runtime_tool
from fluentytdl.core.yt_dlp_cli import resolve_yt_dlp_exe, prepare_yt_dlp_env

print('locate_runtime_tool yt-dlp:')
try:
    print(locate_runtime_tool('yt-dlp.exe','yt-dlp/yt-dlp.exe'))
except Exception as e:
    print('ERROR', e)

print('resolve_yt_dlp_exe:', resolve_yt_dlp_exe())
print('prepare_yt_dlp_env PATH head:', prepare_yt_dlp_env().get('PATH','').split(';')[:3])
