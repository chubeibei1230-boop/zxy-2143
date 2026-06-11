"""
完整的安全修复验证测试 - 修复权限过滤问题
"""
import requests
import json

BASE_URL = "http://127.0.0.1:8043"

def get_token(username, password):
    url = f"{BASE_URL}/api/token/"
    data = {"username": username, "password": password}
    r = requests.post(url, json=data)
    return r.json()["access"] if r.status_code == 200 else None

def print_test(name, passed, message=""):
    status = "✅ 通过" if passed else "❌ 失败"
    print(f"{status} - {name}")
    if message:
        print(f"   详情: {message}")

def create_item(token, title="测试事项"):
    """使用指定token创建事项，返回item_id"""
    submit_data = {
        "title": title,
        "service_type_id": 1,
        "site_id": 1,
        "applicant_name": "测试申请人",
        "applicant_phone": "13800138000",
        "description": "测试描述"
    }
    url = f"{BASE_URL}/api/service/items/submit/"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(url, json=submit_data, headers=headers)
    return r.json()["data"]["id"] if r.status_code == 201 else None

def get_item(token, item_id):
    """获取事项详情（绕过列表过滤）"""
    url = f"{BASE_URL}/api/service/items/{item_id}/"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    return r.json()["data"] if r.status_code == 200 else None

def transition_item(token, item_id, target_status, **kwargs):
    """推进状态"""
    url = f"{BASE_URL}/api/service/items/{item_id}/transition/"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"target_status": target_status, **kwargs}
    r = requests.post(url, json=data, headers=headers)
    return r

def get_audit_logs(token, item_id):
    """获取审计日志"""
    url = f"{BASE_URL}/api/service/items/{item_id}/audit_logs/"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    return r.json()["data"] if r.status_code == 200 else None

def undo_item(token, item_id, audit_log_id):
    """撤销操作"""
    url = f"{BASE_URL}/api/service/items/{item_id}/undo/"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"audit_log_id": audit_log_id}
    r = requests.post(url, json=data, headers=headers)
    return r

def redo_item(token, item_id, audit_log_id):
    """重做操作"""
    url = f"{BASE_URL}/api/service/items/{item_id}/redo/"
    headers = {"Authorization": f"Bearer {token}"}
    data = {"audit_log_id": audit_log_id}
    r = requests.post(url, json=data, headers=headers)
    return r

def test_all():
    print("=" * 60)
    print("公益服务事项管理系统 - 安全修复验证测试")
    print("=" * 60)
    
    admin_token = get_token("admin", "admin123")
    op_a_token = get_token("operator_a", "123456")
    op_b_token = get_token("operator_b", "123456")
    
    if not all([admin_token, op_a_token, op_b_token]):
        print("❌ 获取Token失败")
        return
    
    # ===== 测试1: 提交事项权限 =====
    print("\n=== 测试1: 提交事项权限 ===")
    
    submit_data = {
        "title": "权限测试",
        "service_type_id": 1,
        "site_id": 1,
        "applicant_name": "测试",
        "applicant_phone": "13800138000",
        "description": "测试"
    }
    url = f"{BASE_URL}/api/service/items/submit/"
    
    r = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {admin_token}"})
    print_test("管理员可以提交事项", r.status_code == 201, f"状态码: {r.status_code}")
    
    r = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {op_a_token}"})
    print_test("录入员可以提交事项", r.status_code == 201, f"状态码: {r.status_code}")
    
    r = requests.post(url, json=submit_data, headers={"Authorization": f"Bearer {op_b_token}"})
    print_test("复核员不能提交事项", r.status_code == 403, f"状态码: {r.status_code}")
    
    # ===== 测试2: 关闭事项权限 =====
    print("\n=== 测试2: 关闭事项权限 ===")
    
    item_id = create_item(op_a_token, "关闭权限测试")
    if not item_id:
        print("❌ 创建测试事项失败")
        return
    
    transition_item(op_a_token, item_id, "PROCESSING")
    transition_item(op_a_token, item_id, "PENDING_REVIEW", handler_note="处理完成")
    
    item = get_item(op_a_token, item_id)
    print_test("事项状态为待复核", item["status"] == "PENDING_REVIEW", f"当前状态: {item['status_display']}")
    
    r = transition_item(op_a_token, item_id, "CLOSED", review_note="录入员尝试关闭")
    print_test("录入员不能关闭事项", r.status_code in [400, 403], 
               f"状态码: {r.status_code}, 消息: {r.json().get('message', '')}")
    
    item = get_item(op_a_token, item_id)
    print_test("事项状态仍为待复核", item["status"] == "PENDING_REVIEW", f"当前状态: {item['status_display']}")
    
    r = transition_item(op_b_token, item_id, "CLOSED", review_note="复核通过")
    print_test("复核员可以关闭事项", r.status_code == 200, f"状态码: {r.status_code}, 消息: {r.json().get('message', '')}")
    
    item = get_item(admin_token, item_id)
    print_test("事项状态已关闭", item["status"] == "CLOSED", f"当前状态: {item['status_display']}")
    
    # ===== 测试3: 撤销只能撤销最近的操作 =====
    print("\n=== 测试3: 撤销只能撤销最近的操作 ===")
    
    item_id2 = create_item(op_a_token, "撤销测试事项")
    if not item_id2:
        print("❌ 创建测试事项失败")
        return
    
    transition_item(op_a_token, item_id2, "PROCESSING")
    transition_item(op_a_token, item_id2, "PENDING_REVIEW", handler_note="处理完成")
    
    logs = get_audit_logs(op_a_token, item_id2)
    non_undo_logs = [log for log in logs if log["operation_type"] not in ["UNDO", "REDO"]]
    
    if len(non_undo_logs) < 3:
        print(f"❌ 日志数量不足: {len(non_undo_logs)}")
        return
    
    oldest_log_id = non_undo_logs[-1]["id"]
    latest_log_id = non_undo_logs[0]["id"]
    
    print(f"  最早操作ID: {oldest_log_id} (类型: {non_undo_logs[-1]['operation_type_display']})")
    print(f"  最近操作ID: {latest_log_id} (类型: {non_undo_logs[0]['operation_type_display']})")
    
    r = undo_item(op_a_token, item_id2, oldest_log_id)
    print_test("不能撤销非最近的旧操作", r.status_code == 400, 
               f"状态码: {r.status_code}, 消息: {r.json().get('message', '')}")
    
    r = undo_item(op_a_token, item_id2, latest_log_id)
    print_test("可以撤销最近的操作", r.status_code == 200, f"状态码: {r.status_code}")
    
    item = get_item(op_a_token, item_id2)
    print_test("撤销后状态回退到处理中", item["status"] == "PROCESSING", f"当前状态: {item['status_display']}")
    
    # ===== 测试4: 重做权限控制 =====
    print("\n=== 测试4: 重做权限控制 ===")
    
    item_id3 = create_item(op_a_token, "重做权限测试")
    if not item_id3:
        print("❌ 创建测试事项失败")
        return
    
    transition_item(op_a_token, item_id3, "PROCESSING")
    transition_item(op_a_token, item_id3, "PENDING_REVIEW", handler_note="处理完成")
    transition_item(op_b_token, item_id3, "CLOSED", review_note="复核通过")
    
    logs = get_audit_logs(admin_token, item_id3)
    close_log = next((log for log in logs if log["operation_type"] == "STATUS_CHANGE" and log["after_snapshot"].get("status") == "CLOSED"), None)
    
    if not close_log:
        print("❌ 查找关闭操作日志失败")
        print(f"  所有日志: {[(l['id'], l['operation_type'], l['after_snapshot'].get('status')) for l in logs]}")
        return
    
    close_log_id = close_log["id"]
    print(f"  关闭操作ID: {close_log_id}")
    
    r = undo_item(op_b_token, item_id3, close_log_id)
    print_test("复核员可以撤销关闭操作", r.status_code == 200, f"状态码: {r.status_code}, 消息: {r.json().get('message', '')}")
    
    item = get_item(admin_token, item_id3)
    print_test("撤销关闭后状态为待复核", item["status"] == "PENDING_REVIEW", f"当前状态: {item['status_display']}")
    
    r = redo_item(op_a_token, item_id3, close_log_id)
    print_test("录入员不能重做关闭操作", r.status_code in [400, 403], 
               f"状态码: {r.status_code}, 消息: {r.json().get('message', '')}")
    
    item = get_item(admin_token, item_id3)
    print_test("事项状态仍为待复核", item["status"] == "PENDING_REVIEW", f"当前状态: {item['status_display']}")
    
    r = redo_item(op_b_token, item_id3, close_log_id)
    print_test("复核员可以重做关闭操作", r.status_code == 200, f"状态码: {r.status_code}, 消息: {r.json().get('message', '')}")
    
    item = get_item(admin_token, item_id3)
    print_test("事项状态已关闭", item["status"] == "CLOSED", f"当前状态: {item['status_display']}")
    
    print("\n" + "=" * 60)
    print("所有安全修复验证完成！")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_all()
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
