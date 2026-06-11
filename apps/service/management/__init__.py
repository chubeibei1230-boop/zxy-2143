from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from apps.service.models import ServiceType, ServiceSite

User = get_user_model()


class Command(BaseCommand):
    help = '初始化测试数据'

    def handle(self, *args, **options):
        self.stdout.write('开始初始化测试数据...')

        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'role': 'ADMIN',
                'real_name': '系统管理员',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            self.stdout.write(self.style.SUCCESS('创建管理员: admin / admin123'))
        else:
            self.stdout.write('管理员已存在')

        op_a, created = User.objects.get_or_create(
            username='operator_a',
            defaults={
                'role': 'OPERATOR_A',
                'real_name': '录入员张三',
                'is_staff': True,
            }
        )
        if created:
            op_a.set_password('123456')
            op_a.save()
            self.stdout.write(self.style.SUCCESS('创建录入员: operator_a / 123456'))
        else:
            self.stdout.write('录入员已存在')

        op_b, created = User.objects.get_or_create(
            username='operator_b',
            defaults={
                'role': 'OPERATOR_B',
                'real_name': '复核员李四',
                'is_staff': True,
            }
        )
        if created:
            op_b.set_password('123456')
            op_b.save()
            self.stdout.write(self.style.SUCCESS('创建复核员: operator_b / 123456'))
        else:
            self.stdout.write('复核员已存在')

        types_data = [
            {'code': 'WELFARE_001', 'name': '老年人服务', 'description': '针对老年人的公益服务'},
            {'code': 'WELFARE_002', 'name': '残疾人服务', 'description': '针对残疾人的公益服务'},
            {'code': 'WELFARE_003', 'name': '儿童关爱', 'description': '针对困境儿童的关爱服务'},
            {'code': 'WELFARE_004', 'name': '社区帮扶', 'description': '社区居民帮扶服务'},
        ]
        for item in types_data:
            obj, created = ServiceType.objects.get_or_create(code=item['code'], defaults=item)
            if created:
                self.stdout.write(self.style.SUCCESS(f'创建服务类型: {item["name"]}'))

        sites_data = [
            {'code': 'SITE_001', 'name': '中心服务站', 'address': '人民路1号', 'contact': '王主任', 'phone': '010-12345678'},
            {'code': 'SITE_002', 'name': '东区服务站', 'address': '东方路100号', 'contact': '李主任', 'phone': '010-87654321'},
            {'code': 'SITE_003', 'name': '西区服务站', 'address': '西大街200号', 'contact': '赵主任', 'phone': '010-11112222'},
        ]
        for item in sites_data:
            obj, created = ServiceSite.objects.get_or_create(code=item['code'], defaults=item)
            if created:
                self.stdout.write(self.style.SUCCESS(f'创建服务站点: {item["name"]}'))

        self.stdout.write(self.style.SUCCESS('初始化完成！'))
