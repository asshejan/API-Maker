"""
PhantomAPI — Save ChatGPT Session Script

Run this script ONCE to save your logged-in ChatGPT session so the headless
browser can use it without needing to log in every time.

Usage:
    python scripts/save_session.py

A visible Chrome window will open. Log in to ChatGPT, wait until the chat
page loads fully, then press ENTER in this terminal. The session will be saved
to chatgpt_session.json in the project root.
"""

import asyncio
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


OUTPUT_FILE = "chatgpt_session.json"


async def main():
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright not installed. Run: pip install playwright")
        sys.exit(1)

    print("=" * 60)
    print("  PhantomAPI — ChatGPT Session Saver")
    print("=" * 60)
    print()
    print("1. A Chrome window will open and navigate to chatgpt.com")
    print("2. Log in with your account (Google, email, etc.)")
    print("3. Wait until the chat page fully loads (you see the prompt box)")
    print("4. Come back here and press ENTER to save the session")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Must be visible so you can log in
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        print("Opening chatgpt.com...")
        await page.goto("https://chatgpt.com/", wait_until="domcontentloaded")

        print()
        print("👆 Please log in to ChatGPT in the browser window.")
        print("   When fully logged in and the chat box is visible, press ENTER here.")
        print()
        input("  >>> Press ENTER when ready to save session... ")

        # Save the full storage state (cookies + localStorage)
        await context.storage_state(path=OUTPUT_FILE)
        await browser.close()

    print()
    print(f"✅ Session saved to: {OUTPUT_FILE}")
    print()
    print("Next steps:")
    print(f"  • Make sure CHATGPT_STORAGE_STATE={OUTPUT_FILE} is in your .env")
    print("  • Restart the PhantomAPI server")
    print("  • Your requests will now be authenticated automatically")


if __name__ == "__main__":
    asyncio.run(main())
