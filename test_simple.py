"""
简单测试脚本
"""
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.service.services import generate_item_no, create_service_item
from apps.core.models import User

print("测试事项编号生成:")
for i in range(5):
    print(f"  {i+1}: {generate_item_no()}")

print("\n测试创建事项:")
user = User.objects.get(username='admin')
data = {
    'item_no': generate_item_no(),
    'title': '测试事项',
    'service_type_id': 1,
    'site_id': 1,
    'applicant_name': '测试人',
    'applicant_phone': '13800138000',
    'description': '测试描述',
}
try:
    item = create_service_item(data, user)
    print(f"  创建成功! ID={item.id}, 编号={item.item_no}")
except Exception as e:
    print(f"  错误: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
