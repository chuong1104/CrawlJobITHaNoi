from playwright.sync_api import sync_playwright
import time
import warnings
import asyncio

def test():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        # Test 1: what if we return the coroutine in the handler?
        # sync_api route handlers can't return coroutines unless they are declared as async def?
        # Actually playwright's sync_api route dispatcher checks asyncio.iscoroutinefunction()
        pass

if __name__ == "__main__":
    pass
