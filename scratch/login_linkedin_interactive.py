import os
import sys
import json
import time
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright

def main():
    username = os.getenv("LINKEDIN_USERNAME")
    password = os.getenv("LINKEDIN_PASSWORD")
    session_file = Path("linkedin_session.json")

    print("Khởi động Playwright có giao diện (Headed Mode)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, # Hiển thị giao diện để bạn tự nhập mã 2FA
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
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
            print("Không tìm thấy tài khoản trong file .env, vui lòng tự nhập tay trên trình duyệt.")

        print("\n" + "="*60)
        print("VUI LÒNG KIỂM TRA TRÌNH DUYỆT!")
        print("Nếu gặp màn hình 2FA hoặc Captcha, hãy tự giải quyết.")
        print("Script sẽ đợi cho đến khi bạn đăng nhập thành công (chuyển hướng sang trang feed/mynetwork).")
        print("="*60 + "\n")

        # Chờ đến khi URL đổi sang feed hoặc mynetwork, tối đa 5 phút
        try:
            page.wait_for_url("**/feed/**", timeout=300000)
            print("Đăng nhập thành công! Đang lưu session cookie...")
        except Exception:
            print("Hết thời gian chờ (5 phút) hoặc URL không đúng. Vui lòng đóng trình duyệt và thử lại.")
            browser.close()
            return

        cookies = context.cookies()
        with open(session_file, "w") as f:
            json.dump(cookies, f)
            
        print(f"Lưu session thành công vào: {session_file.absolute()}")
        print("Bây giờ bạn có thể chạy lại lệnh docker compose để test!")
        
        browser.close()

if __name__ == "__main__":
    main()
