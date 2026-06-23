import os
import sys
import json
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parents[1]))
load_dotenv()

from curl_cffi import requests

def load_cookies_to_session(session, session_file_paths):
    for path in session_file_paths:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                raw_cookies = []
                if isinstance(data, list):
                    raw_cookies = data
                elif isinstance(data, dict) and "cookies" in data:
                    raw_cookies = data["cookies"]
                elif isinstance(data, dict):
                    # Dạng phẳng {name: value} từ curl_cffi
                    raw_cookies = [{"name": k, "value": v, "domain": ".linkedin.com", "path": "/"} for k, v in data.items()]
                
                for cookie in raw_cookies:
                    name = cookie.get("name")
                    value = cookie.get("value")
                    domain = cookie.get("domain", ".linkedin.com")
                    if name and value:
                        session.cookies.set(name, value, domain=domain)
                print(f"Đã load cookies thành công từ {path}")
                return True
            except Exception as e:
                print(f"Lỗi load cookie từ {path}: {e}")
    return False

def main():
    username = os.getenv("LINKEDIN_USERNAME")
    password = os.getenv("LINKEDIN_PASSWORD")
    
    session_file_paths = [
        Path("data/linkedin_session.json"),
        Path("data/www.linkedin.com_23-06-2026.json"),
        Path("linkedin_session.json"),
        Path("www.linkedin.com_23-06-2026.json"),
        Path("scratch/linkedin_session.json"),
        Path("scratch/www.linkedin.com_23-06-2026.json"),
    ]

    print("Khởi tạo session curl_cffi (impersonate='chrome110')...")
    session = requests.Session(impersonate="chrome110")

    # Thử load cookies trước
    if load_cookies_to_session(session, session_file_paths):
        print("Kiểm tra trạng thái đăng nhập bằng cookies...")
        r_check = session.get("https://www.linkedin.com/feed/", allow_redirects=False)
        if r_check.status_code == 200 or (r_check.status_code == 302 and 'feed' in r_check.headers.get('Location', '')):
            print("=> SỬ DỤNG COOKIES THÀNH CÔNG! Bỏ qua đăng nhập bằng mật khẩu.")
            return
        else:
            print(f"Cookies đã hết hạn hoặc không hợp lệ (status: {r_check.status_code}, location: {r_check.headers.get('Location', 'N/A')}). Tiến hành đăng nhập bằng mật khẩu.")

    if not username or not password:
        print("Vui lòng cấu hình LINKEDIN_USERNAME và LINKEDIN_PASSWORD trong file .env")
        return

    print("GET https://www.linkedin.com/checkpoint/rm/sign-in-another-account ...")
    r1 = session.get("https://www.linkedin.com/checkpoint/rm/sign-in-another-account")
    if r1.status_code != 200:
        print(f"Lỗi truy cập trang đăng nhập, status: {r1.status_code}")
        return

    soup = BeautifulSoup(r1.text, 'html.parser')
    
    # Tìm thẻ form đăng nhập (tìm form chứa thẻ input name='session_key')
    login_form = None
    for form in soup.find_all('form'):
        if form.find('input', {'name': 'session_key'}):
            login_form = form
            break
    
    if not login_form:
        print("Không tìm thấy form đăng nhập. LinkedIn có thể đã thay đổi giao diện hoặc chặn request.")
        return

    action_url = login_form.get('action') or "https://www.linkedin.com/checkpoint/rm/sign-in-submit"
    if not action_url.startswith('http'):
        action_url = "https://www.linkedin.com" + action_url

    print(f"Login URL: {action_url}")

    # Lấy tất cả các input hidden cần thiết (csrf, token, v.v.)
    payload = {}
    for input_tag in login_form.find_all('input'):
        name = input_tag.get('name')
        value = input_tag.get('value', '')
        if name:
            payload[name] = value

    # Ghi đè username và password
    payload['session_key'] = username
    payload['session_password'] = password

    print("Đang gửi POST request đăng nhập...")
    r2 = session.post(action_url, data=payload, allow_redirects=False)

    print(f"Mã trạng thái phản hồi: {r2.status_code}")
    if 'Location' in r2.headers:
        redirect_url = r2.headers['Location']
        print(f"Chuyển hướng đến: {redirect_url}")
        
        if 'challenge' in redirect_url or 'checkpoint' in redirect_url:
            print("=> THẤT BẠI: Tài khoản của bạn bị chặn bởi cơ chế bảo mật (Checkpoint/2FA) của LinkedIn.")
            print("   (Request tự động bị LinkedIn phát hiện và yêu cầu xác minh)")
            return
        elif 'feed' in redirect_url or 'mynetwork' in redirect_url:
            print("=> ĐĂNG NHẬP THÀNH CÔNG!")
            # Lưu session
            with open(session_file, "w") as f:
                json.dump(session.cookies.get_dict(), f)
            print(f"Đã lưu cookie vào {session_file}")
            return
            
    print("=> Phản hồi không rõ ràng, có thể đăng nhập đã thất bại.")
    print("Bạn có thể kiểm tra HTML trả về nếu cần thiết.")

if __name__ == "__main__":
    main()
