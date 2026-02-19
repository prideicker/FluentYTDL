
import sys
import os

# Add src to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from fluentytdl.auth.cookie_cleaner import CookieCleaner

def test_cookie_cleaner():
    print("Testing CookieCleaner...")

    # Mock cookies
    raw_cookies = [
        # Should keep (YouTube)
        {"domain": ".youtube.com", "name": "SID", "value": "123", "path": "/", "secure": True, "expires": 1234567890, "extra": "remove_me"},
        {"domain": "youtube.com", "name": "__Secure-3PSID", "value": "abc", "path": "/", "secure": True},
        {"domain": ".google.com", "name": "HSID", "value": "xyz", "path": "/", "secure": True},
        
        # Should remove (Wrong domain)
        {"domain": ".example.com", "name": "SID", "value": "bad", "path": "/"},
        
        # Should remove (Wrong name for YouTube)
        {"domain": ".youtube.com", "name": "BAD_COOKIE", "value": "bad", "path": "/"},
        
        # Should keep (Bilibili - only domain check implemented)
        {"domain": ".bilibili.com", "name": "SESSDATA", "value": "bili", "path": "/"},
    ]

    # Test YouTube cleaning
    print("\n[Test 1] Cleaning for YouTube...")
    cleaned_yt = CookieCleaner.clean(raw_cookies, "youtube")
    
    # Assertions
    allowed_names = {"SID", "__Secure-3PSID", "HSID"}
    
    for c in cleaned_yt:
        print(f"  Kept: {c.get('domain')} - {c.get('name')}")
        # Check integrity
        assert c["name"] in allowed_names, f"Unexpected cookie kept: {c['name']}"
        assert c["domain"] in {".youtube.com", "youtube.com", ".google.com"}, f"Unexpected domain kept: {c['domain']}"
        assert "extra" not in c, "Extra fields not removed"
        
    assert len(cleaned_yt) == 3, f"Expected 3 cookies, got {len(cleaned_yt)}"
    print("  => YouTube cleaning PASSED")

    # Test Bilibili cleaning
    print("\n[Test 2] Cleaning for Bilibili...")
    cleaned_bili = CookieCleaner.clean(raw_cookies, "bilibili")
    
    for c in cleaned_bili:
         print(f"  Kept: {c.get('domain')} - {c.get('name')}")
         assert c["domain"] == ".bilibili.com", f"Unexpected domain: {c['domain']}"
    
    assert len(cleaned_bili) == 1, f"Expected 1 cookie, got {len(cleaned_bili)}"
    print("  => Bilibili cleaning PASSED")

if __name__ == "__main__":
    try:
        test_cookie_cleaner()
        print("\nAll tests passed!")
    except AssertionError as e:
        print(f"\nTEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
