@echo off
echo ========================================
echo 公益服务事项管理系统 - 启动脚本
echo ========================================
echo.

echo [1/4] 检查 Python 环境...
python --version
if errorlevel 1 (
    echo 错误: 未检测到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

echo.
echo [2/4] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo 警告: 部分依赖安装失败，尝试继续...
)

echo.
echo [3/4] 数据库迁移...
python manage.py makemigrations
python manage.py migrate

echo.
echo [4/4] 启动服务 (端口 8043)...
echo.
echo 服务启动后，请访问:
echo   API 根路径:  http://127.0.0.1:8043/api/
echo   管理后台:    http://127.0.0.1:8043/admin/
echo.
echo JWT 获取:     POST http://127.0.0.1:8043/api/token/
echo                Body: {"username": "admin", "password": "admin123"}
echo.
python manage.py runserver 0.0.0.0:8043
pause
