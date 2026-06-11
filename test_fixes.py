"""
测试脚本：验证所有安全修复
运行方式：python test_fixes.py
"""
import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8043"

def get_token(username, password):
    url = f"{BASE_URL}/api/token/"
    data = {"username": username, "password": password}
    r = requests.post(url, json=data)
    if r.status_code == 200:
        return r.json()["access"]
    else:
        print(f"获取 {username} Token 失败: {r.status_code} {r.text}")
        return None

def print_test(name, passed, message=""):
    status = "✅ 通过" if passed else "❌ 失败"
    print(f"{status} - {name}")
    if message:
        print(f"   详情: {message}")

def test_1_submit_permission():
    """测试1: 提交事项权限 - 只有录入员和管理员可以提交"""
    print("\n=== 测试1: 提交事项权限 ===")
    
    admin_token = get_token("admin", "admin123")
    op_a_token = get_token("operator_a", "123456")
    op_b_token = get_token("operator_b", "123456")
    
    if not all([admin_token, op_a_token, op_b_token]):
        print_test("获取测试Token", False)
        return
    
    submit_data = {
        "title": "测试事项",
        "service_type_id": 1,
        "site_id": 1,
        "applicant_name": "测试申请人",
        "applicant_phone": "13800138000",
        "description": "测试描述"
    }
    
    url = f"{BASE_URL}/api/service/items/submit/"
    
    r_admin = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {admin_token}"})
    print_test("管理员提交事项", r_admin.status_code == 201, f"状态码: {r_admin.status_code}")
    
    r_op_a = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {op_a_token}"})
    print_test("录入员提交事项", r_op_a.status_code == 201, f"状态码: {r_op_a.status_code}")
    
    r_op_b = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {op_b_token}"})
    print_test("复核员不能提交事项", r_op_b.status_code in [401, 403], f"状态码: {r_op_b.status_code}")

def test_2_close_permission():
    """测试2: 关闭事项权限 - 只有复核员和管理员可以关闭"""
    print("\n=== 测试2: 关闭事项权限 ===")
    
    admin_token = get_token("admin", "admin123")
    op_a_token = get_token("operator_a", "123456")
    op_b_token = get_token("operator_b", "123456")
    
    if not all([admin_token, op_a_token, op_b_token]):
        return
    
    submit_data = {
        "title": "权限测试事项",
        "service_type_id": 1,
        "site_id": 1,
        "applicant_name": "测试人",
        "applicant_phone": "13800138000",
        "description": "权限测试"
    }
    
    url = f"{BASE_URL}/api/service/items/submit/"
    r = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {admin_token}"})
    if r.status_code != 201:
        print_test("创建测试事项", False, f"状态码: {r.status_code}")
        return
    
    item_id = r.json()["data"]["id"]
    
    trans_url = f"{BASE_URL}/api/service/items/{item_id}/transition/"
    
    r1 = requests.post(trans_url, json={"target_status": "PROCESSING"}, headers={"Authorization": f"Bearer {admin_token}"})
    if r1.status_code != 200:
        print_test("推进到处理中", False, f"状态码: {r1.status_code} {r1.text}")
        return
    
    r2 = requests.post(trans_url, json={"target_status": "PENDING_REVIEW", "handler_note": "处理完成"}, headers={"Authorization": f"Bearer {admin_token}"})
    if r2.status_code != 200:
        print_test("推进到待复核", False, f"状态码: {r2.status_code} {r2.text}")
        return
    
    r3 = requests.post(trans_url, json={"target_status": "CLOSED", "review_note": "复核通过"}, headers={"Authorization": f"Bearer {op_a_token}"})
    print_test("录入员不能关闭事项", r3.status_code in [400, 403], f"状态码: {r3.status_code}, 响应: {r3.json().get('message', '')}")
    
    r4 = requests.post(trans_url, json={"target_status": "CLOSED", "review_note": "复核通过"}, headers={"Authorization": f"Bearer {op_b_token}"})
    print_test("复核员可以关闭事项", r4.status_code == 200, f"状态码: {r4.status_code}")

def test_3_undo_only_latest():
    """测试3: 撤销只能撤销最近的操作，不能撤销任意旧历史"""
    print("\n=== 测试3: 撤销只能撤销最近的操作 ===")
    
    admin_token = get_token("admin", "admin123")
    if not admin_token:
        return
    
    submit_data = {
        "title": "撤销测试事项",
        "service_type_id": 1,
        "site_id": 1,
        "applicant_name": "测试人",
        "applicant_phone": "13800138000",
        "description": "撤销测试"
    }
    
    url = f"{BASE_URL}/api/service/items/submit/"
    r = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {admin_token}"})
    if r.status_code != 201:
        print_test("创建测试事项", False)
        return
    
    item_id = r.json()["data"]["id"]
    
    trans_url = f"{BASE_URL}/api/service/items/{item_id}/transition/"
    audit_url = f"{BASE_URL}/api/service/items/{item_id}/audit_logs/"
    
    requests.post(trans_url, json={"target_status": "PROCESSING"}, headers={"Authorization": f"Bearer {admin_token}"})
    requests.post(trans_url, json={"target_status": "PENDING_REVIEW", "handler_note": "处理完成"}, headers={"Authorization": f"Bearer {admin_token}"})
    
    r_audit = requests.get(audit_url, headers={"Authorization": f"Bearer {admin_token}"})
    logs = r_audit.json()["data"]
    
    non_undo_logs = [log for log in logs if log["operation_type"] not in ["UNDO", "REDO"]]
    if len(non_undo_logs) < 3:
        print_test("获取审计日志", False, f"日志数量: {len(non_undo_logs)}")
        return
    
    first_log_id = non_undo_logs[-1]["id"]
    latest_log_id = non_undo_logs[0]["id"]
    
    undo_url = f"{BASE_URL}/api/service/items/{item_id}/undo/"
    
    r1 = requests.post(undo_url, json={"audit_log_id": first_log_id}, headers={"Authorization": f"Bearer {admin_token}"})
    print_test("不能撤销非最近的旧操作", r1.status_code in [400, 403], 
               f"状态码: {r1.status_code}, 消息: {r1.json().get('message', '')}")
    
    r2 = requests.post(undo_url, json={"audit_log_id": latest_log_id}, headers={"Authorization": f"Bearer {admin_token}"})
    print_test("可以撤销最近的操作", r2.status_code == 200, f"状态码: {r2.status_code}")

def test_4_redo_permission():
    """测试4: 重做权限 - 录入员不能重做关闭操作"""
    print("\n=== 测试4: 重做权限控制 ===")
    
    admin_token = get_token("admin", "admin123")
    op_a_token = get_token("operator_a", "123456")
    op_b_token = get_token("operator_b", "123456")
    
    if not all([admin_token, op_a_token, op_b_token]):
        return
    
    submit_data = {
        "title": "重做权限测试事项",
        "service_type_id": 1,
        "site_id": 1,
        "applicant_name": "测试人",
        "applicant_phone": "13800138000",
        "description": "重做权限测试"
    }
    
    url = f"{BASE_URL}/api/service/items/submit/"
    r = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {admin_token}"})
    if r.status_code != 201:
        print_test("创建测试事项", False)
        return
    
    item_id = r.json()["data"]["id"]
    
    trans_url = f"{BASE_URL}/api/service/items/{item_id}/transition/"
    audit_url = f"{BASE_URL}/api/service/items/{item_id}/audit_logs/"
    undo_url = f"{BASE_URL}/api/service/items/{item_id}/undo/"
    redo_url = f"{BASE_URL}/api/service/items/{item_id}/redo/"
    
    requests.post(trans_url, json={"target_status": "PROCESSING"}, headers={"Authorization": f"Bearer {admin_token}"})
    requests.post(trans_url, json={"target_status": "PENDING_REVIEW", "handler_note": "处理完成"}, headers={"Authorization": f"Bearer {admin_token}"})
    requests.post(trans_url, json={"target_status": "CLOSED", "review_note": "复核通过"}, headers={"Authorization": f"Bearer {op_b_token}"})
    
    r_audit = requests.get(audit_url, headers={"Authorization": f"Bearer {admin_token}"})
    logs = r_audit.json()["data"]
    close_log = next((log for log in logs if log["after_snapshot"].get("status") == "CLOSED" and log["operation_type"] == "STATUS_CHANGE"), None)
    
    if not close_log:
        print_test("查找关闭操作日志", False)
        return
    
    close_log_id = close_log["id"]
    
    r_undo = requests.post(undo_url, json={"audit_log_id": close_log_id}, headers={"Authorization": f"Bearer {op_b_token}"})
    if r_undo.status_code != 200:
        print_test("复核员撤销关闭操作", False, f"状态码: {r_undo.status_code}, {r_undo.text}")
        return
    print_test("复核员撤销关闭操作", True)
    
    r_audit2 = requests.get(audit_url, headers={"Authorization": f"Bearer {admin_token}"})
    logs2 = r_audit2.json()["data"]
    undone_close_log = next((log for log in logs2 if log["id"] == close_log_id), None)
    if not undone_close_log or not undone_close_log["is_undone"]:
        print_test("确认关闭操作已被撤销", False)
        return
    
    r_redo_op_a = requests.post(redo_url, json={"audit_log_id": close_log_id}, headers={"Authorization": f"Bearer {op_a_token}"})
    print_test("录入员不能重做关闭操作", r_redo_op_a.status_code in [400, 403], 
               f"状态码: {r_redo_op_a.status_code}, 消息: {r_redo_op_a.json().get('message', '')}")
    
    r_redo_op_b = requests.post(redo_url, json={"audit_log_id": close_log_id}, headers={"Authorization": f"Bearer {op_b_token}"})
    print_test("复核员可以重做关闭操作", r_redo_op_b.status_code == 200, f"状态码: {r_redo_op_b.status_code}")

if __name__ == "__main__":
    print("=" * 60)
    print("公益服务事项管理系统 - 安全修复验证测试")
    print("=" * 60)
    
    try:
        test_1_submit_permission()
        test_2_close_permission()
        test_3_undo_only_latest()
        test_4_redo_permission()
        
        print("\n" + "=" * 60)
        print("测试完成！")
        print("=" * 60)
    except requests.exceptions.ConnectionError:
        print("\n❌ 无法连接到服务器，请确保服务器已启动在端口 8043")
        print("启动命令: python manage.py runserver 0.0.0.0:8043")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
