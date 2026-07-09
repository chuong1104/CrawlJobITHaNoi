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
    session_file = Path("data/auth/linkedin_session.json")
    session_file.parent.mkdir(parents=True, exist_ok=True)

    print("Khoi dong Playwright (Headed Mode)...")
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

        print("Truy cap trang dang nhap LinkedIn...")
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")

        if username and password:
            print("Dang dien thong tin tai khoan...")
            autofill_success = False
            try:
                # Thử với giao diện đăng nhập /login
                page.wait_for_selector("#username", timeout=5000)
                page.fill("#username", username)
                page.fill("#password", password)
                page.click('button[type="submit"]')
                autofill_success = True
            except Exception:
                try:
                    # Thử với giao diện trang chủ hoặc authwall
                    page.wait_for_selector("#session_key", timeout=5000)
                    page.fill("#session_key", username)
                    page.fill("#session_password", password)
                    page.click('button[type="submit"]')
                    autofill_success = True
                except Exception:
                    pass
            
            if not autofill_success:
                print("Khong the tu dong dien tai khoan (co the giao dien LinkedIn khac hoac mang cham).")
                print("Vui long tu nhap Email/Mat khau truc tiep tren cua so trinh duyet vua mo.")
        else:
            print("Khong tim thay tai khoan trong .env, vui long tu nhap tay tren trinh duyet.")

        print("\n" + "=" * 60)
        print("VUI LONG KIEM TRA TRINH DUYET!")
        print("Neu gap man hinh 2FA/Captcha, hay tu giai quyet.")
        print("Script doi den khi dang nhap thanh cong (toi da 5 phut).")
        print("=" * 60 + "\n")

        try:
            page.wait_for_url("**/feed/**", timeout=300_000)
            print("Dang nhap thanh cong! Dang luu session cookie...")
        except Exception:
            print("Het thoi gian cho. Vui long thu lai.")
            browser.close()
            return

        cookies = context.cookies()
        with open(session_file, "w") as f:
            json.dump(cookies, f)

        print(f"Luu session thanh cong vao: {session_file.absolute()}")
        browser.close()


if __name__ == "__main__":
    main()
