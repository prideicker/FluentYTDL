import sys
import os

# Add src to sys.path
sys.path.append(os.path.join(os.getcwd(), "src"))

from fluentytdl.core.dependency_manager import dependency_manager, UpdateCheckerWorker

def test_ffmpeg_version_extraction():
    print("Testing FFmpeg remote version extraction...")
    try:
        # Create a worker instance (requires key and manager)
        worker = UpdateCheckerWorker("ffmpeg", dependency_manager)
        tag, url = worker._get_remote_version("ffmpeg")
        print(f"Result: Tag='{tag}', URL='{url}'")
        
        if tag == "latest":
            print("FAIL: Still returning 'latest'. Logic invalid.")
        else:
            print(f"SUCCESS: Extracted version '{tag}'.")
            
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    test_ffmpeg_version_extraction()
