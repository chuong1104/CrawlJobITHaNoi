import os
from curl_cffi import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

email = os.getenv("ITVIEC_EMAIL")
password = os.getenv("ITVIEC_PASSWORD")

session = requests.Session(impersonate="chrome110")

print("Fetching sign_in page...")
r = session.get("https://itviec.com/sign_in")
print(f"Status: {r.status_code}")

soup = BeautifulSoup(r.text, 'html.parser')
csrf_token = soup.find('meta', {'name': 'csrf-token'})
if csrf_token:
    token = csrf_token['content']
    print(f"Found CSRF token: {token[:10]}...")
else:
    print("No CSRF token found.")

# Let's try to post
data = {
    "authenticity_token": token,
    "user[email]": email,
    "user[password]": password,
    "commit": "Sign In"
}

print("Posting login...")
r2 = session.post("https://itviec.com/sign_in", data=data, allow_redirects=False)
print(f"Post status: {r2.status_code}")
print(f"Redirect location: {r2.headers.get('Location')}")

# Try to get dashboard
r3 = session.get("https://itviec.com/profile")
print(f"Profile status: {r3.status_code}")
print("If profile has my name, login succeeded.")
