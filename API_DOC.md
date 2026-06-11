# 公益服务事项全生命周期管理 API

基于 Django + DRF 的纯后端 API 服务，用于公益服务事项的全生命周期管理。

## 快速启动

### Windows
```bash
start.bat
```

### 手动启动
```bash
pip install -r requirements.txt
python manage.py makemigrations
python manage.py migrate
python manage.py init_data    # 可选：初始化测试数据
python manage.py runserver 0.0.0.0:8043
```

## JWT 认证说明

### 获取 Token
```
POST /api/token/
Content-Type: application/json

{
    "username": "admin",
    "password": "admin123"
}
```

响应：
```json
{
    "refresh": "eyJ0eXAiOiJKV1QiLC...",
    "access": "eyJ0eXAiOiJKV1QiLC..."
}
```

### 使用 Token
在请求头中添加：
```
Authorization: Bearer <access_token>
```

### 刷新 Token
```
POST /api/token/refresh/
Content-Type: application/json

{
    "refresh": "<refresh_token>"
}
```

## 测试账号

| 用户名 | 密码 | 角色 | 说明 |
|--------|------|------|------|
| admin | admin123 | 管理员 | 维护服务类型、站点、状态流转规则 |
| operator_a | 123456 | 录入员 | 创建事项、填写初始信息、推进状态 |
| operator_b | 123456 | 复核员 | 复核处理结果、确认关闭 |

## 统一响应格式

```json
{
    "code": 0,
    "message": "success",
    "data": {}
}
```

- `code`: 0 表示成功，非 0 表示错误
- `message`: 提示信息
- `data`: 返回数据

## 状态流转规则

事项状态严格按照以下顺序单向演进：
```
待受理(PENDING_ACCEPT) → 处理中(PROCESSING) → 待复核(PENDING_REVIEW) → 已关闭(CLOSED)
```

任何非终态都可以跳转到：
```
已取消(CANCELLED) ← 任意非终态
```

终态（已关闭、已取消）不可再变更。

## 主要接口

### 事项相关

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| POST | `/api/service/items/submit/` | 提交事项 | 录入员/管理员 |
| GET | `/api/service/items/` | 事项列表 | 所有登录用户 |
| GET | `/api/service/items/{id}/` | 事项详情 | 所有登录用户 |
| POST | `/api/service/items/{id}/transition/` | 推进状态 | 按角色控制 |
| POST | `/api/service/items/{id}/update_fields/` | 更新字段 | 相关负责人 |
| POST | `/api/service/items/{id}/undo/` | 撤销操作 | 按角色控制 |
| POST | `/api/service/items/{id}/redo/` | 重做操作 | 按角色控制 |
| GET | `/api/service/items/{id}/audit_logs/` | 审计历史 | 所有登录用户 |

### 管理接口

| 方法 | 路径 | 说明 | 权限 |
|------|------|------|------|
| GET/POST | `/api/service/service-types/` | 服务类型列表/创建 | 管理员 |
| GET/PUT/DELETE | `/api/service/service-types/{id}/` | 服务类型详情/更新/删除 | 管理员 |
| GET/POST | `/api/service/sites/` | 服务站点列表/创建 | 管理员 |
| GET/PUT/DELETE | `/api/service/sites/{id}/` | 服务站点详情/更新/删除 | 管理员 |
| GET/POST | `/api/core/users/` | 用户列表/创建 | 管理员 |
| GET | `/api/core/users/me/` | 当前用户信息 | 所有登录用户 |

## 请求示例

### 1. 提交事项
```
POST /api/service/items/submit/
Authorization: Bearer <token>
Content-Type: application/json

{
    "title": "老年人探访服务申请",
    "service_type_id": 1,
    "site_id": 1,
    "applicant_name": "王大爷",
    "applicant_phone": "13800138000",
    "applicant_id_card": "110101194001011234",
    "description": "申请每周上门探访一次",
    "appointment_time": "2024-01-15T10:00:00"
}
```

### 2. 推进状态（待受理 → 处理中）
```
POST /api/service/items/1/transition/
Authorization: Bearer <token>
Content-Type: application/json

{
    "target_status": "PROCESSING",
    "note": "已受理，安排张三负责处理",
    "assignee_id": 2
}
```

### 3. 撤销操作
```
POST /api/service/items/1/undo/
Authorization: Bearer <token>
Content-Type: application/json

{
    "audit_log_id": 5
}
```

### 4. 查看审计历史
```
GET /api/service/items/1/audit_logs/
Authorization: Bearer <token>
```
