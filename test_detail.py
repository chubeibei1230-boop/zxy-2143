"""详细测试"""
import requests

BASE_URL = "http://127.0.0.1:8043"

def get_token(username, password):
    url = f"{BASE_URL}/api/token/"
    data = {"username": username, "password": password}
    r = requests.post(url, json=data)
    print(f"Token请求 {username}: {r.status_code}")
    if r.status_code == 200:
        return r.json()["access"]
    print(f"  响应: {r.text}")
    return None

token = get_token("admin", "admin123")
if not token:
    exit(1)

submit_data = {
    "title": "测试事项",
    "service_type_id": 1,
    "site_id": 1,
    "applicant_name": "测试申请人",
    "applicant_phone": "13800138000",
    "description": "测试描述"
}

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

url = f"{BASE_URL}/api/service/items/submit/"
print(f"\n提交事项...")
r = requests.post(url, json=submit_data, headers=headers)
print(f"状态码: {r.status_code}")
print(f"响应头: {dict(r.headers)}")
print(f"响应内容: {r.text}")

try:
    print(f"JSON: {r.json()}")
except:
    pass
