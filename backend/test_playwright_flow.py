"""
Standalone test: verify Playwright external retrieval pipeline works end-to-end.
Run: python test_playwright_flow.py
"""
import sys
import os

# Add backend to path so imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.external_retrieval import run_external_pipeline, EXTERNAL_RETRIEVAL_ENABLED

def main():
    print("=" * 80)
    print("PLAYWRIGHT EXTERNAL RETRIEVAL TEST")
    print("=" * 80)
    print(f"EXTERNAL_RETRIEVAL_ENABLED: {EXTERNAL_RETRIEVAL_ENABLED}")
    
    if not EXTERNAL_RETRIEVAL_ENABLED:
        print("\n[ERROR] EXTERNAL_RETRIEVAL_ENABLED is False. Set it to true in .env")
        return
    
    test_query = "Who invented the electric light bulb"
    print(f"\nTest query: '{test_query}'")
    print("Running Playwright pipeline (this takes 10-30 seconds)...")
    print("-" * 80)
    
    try:
        results = run_external_pipeline(test_query, top_n_pages=2)
        print("-" * 80)
        print(f"\n[RESULT] Got {len(results)} evidence chunks")
        
        if results:
            print("\nFirst 3 evidence samples:")
            for i, item in enumerate(results[:3], 1):
                snippet = item.get("snippet", "")[:200]
                source = item.get("source_url", "")[:60]
                print(f"\n  {i}. Source: {source}")
                print(f"     Snippet: {snippet}...")
        else:
            print("\n[WARNING] No evidence returned. Check:")
            print("  1. Playwright is installed: pip install playwright")
            print("  2. Chromium is installed: playwright install chromium")
            print("  3. Network access (not behind firewall blocking Google)")
            print("  4. Check logs above for [EXTERNAL_RETRIEVAL] messages")
            
    except Exception as e:
        print(f"\n[ERROR] Pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        print("\nCommon fixes:")
        print("  - pip install playwright")
        print("  - playwright install chromium")
        print("  - Check .env has EXTERNAL_RETRIEVAL_ENABLED=true")

if __name__ == "__main__":
    main()
