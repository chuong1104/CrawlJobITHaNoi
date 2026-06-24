"""
login_linkedin_interactive.py — Đăng nhập LinkedIn thủ công (có giao diện)
để lấy session cookie dùng cho scraper.

Usage:
    python scripts/login_linkedin_interactive.py
"""
import os
import json
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright


def main():
    username = os.getenv("LINKEDIN_USERNAME")
    password = os.getenv("LINKEDIN_PASSWORD")
    session_file = Path("data/linkedin_session.json")
    session_file.parent.mkdir(parents=True, exist_ok=True)

    print("Khởi động Playwright có giao diện (Headed Mode)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,  # Hiển thị giao diện để tự nhập mã 2FA
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            )
        )
        page = context.new_page()

        print("Truy cập trang đăng nhập LinkedIn...")
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        if username and password:
            print("Đang điền thông tin tài khoản...")
            page.fill("#username", username)
            page.fill("#password", password)
            page.click('button[type="submit"]')
        else:
            print("Không tìm thấy tài khoản trong .env, vui lòng tự nhập tay trên trình duyệt.")

        print("\n" + "=" * 60)
        print("VUI LÒNG KIỂM TRA TRÌNH DUYỆT!")
        print("Nếu gặp màn hình 2FA/Captcha, hãy tự giải quyết.")
        print("Script đợi đến khi đăng nhập thành công (tối đa 5 phút).")
        print("=" * 60 + "\n")

        try:
            page.wait_for_url("**/feed/**", timeout=300_000)
            print("Đăng nhập thành công! Đang lưu session cookie...")
        except Exception:
            print("Hết thời gian chờ. Vui lòng thử lại.")
            browser.close()
            return

        cookies = context.cookies()
        with open(session_file, "w") as f:
            json.dump(cookies, f)

        print(f"Lưu session thành công vào: {session_file.absolute()}")
        browser.close()


if __name__ == "__main__":
    main()
