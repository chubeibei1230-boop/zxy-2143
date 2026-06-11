from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    ADMIN = 'ADMIN', '管理员'
    OPERATOR_A = 'OPERATOR_A', '录入员'
    OPERATOR_B = 'OPERATOR_B', '复核员'


class User(AbstractUser):
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR_A,
        verbose_name='角色',
    )
    phone = models.CharField(max_length=20, blank=True, verbose_name='手机号')
    real_name = models.CharField(max_length=50, blank=True, verbose_name='真实姓名')

    class Meta:
        db_table = 'sys_user'
        verbose_name = '用户'
        verbose_name_plural = verbose_name

    def __str__(self):
        return f'{self.username}({self.get_role_display()})'

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def is_operator_a(self):
        return self.role == Role.OPERATOR_A

    @property
    def is_operator_b(self):
        return self.role == Role.OPERATOR_B
