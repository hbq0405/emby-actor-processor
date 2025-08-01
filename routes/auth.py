# routes/auth.py

from flask import Blueprint, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
import secrets

# 导入底层和共享模块
import db_handler
import config_manager
import constants
from extensions import login_required

# 1. 创建蓝图
auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')
logger = logging.getLogger(__name__)

# 2. 将 init_auth 函数迁移到这里，因为它与认证功能紧密相关
def init_auth():
    """初始化认证系统，检查并创建默认用户。"""
    auth_enabled = config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_AUTH_ENABLED, False)
    env_username = os.environ.get("AUTH_USERNAME")
    
    if env_username:
        username = env_username.strip()
    else:
        username = config_manager.APP_CONFIG.get(constants.CONFIG_OPTION_AUTH_USERNAME, constants.DEFAULT_USERNAME).strip()

    if not auth_enabled:
        logger.info("用户认证功能未启用。")
        return

    try:
        with db_handler.get_db_connection(config_manager.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
            
            if user is None:
                random_password = secrets.token_urlsafe(12)
                password_hash = generate_password_hash(random_password)
                cursor.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, password_hash)
                )
                conn.commit()
                logger.critical("=" * 60)
                logger.critical(f"首次运行，已为用户 '{username}' 自动生成初始密码。")
                logger.critical(f"用户名: {username}")
                logger.critical(f"初始密码: {random_password}")
                logger.critical("请立即使用此密码登录，并在设置页面修改。")
                logger.critical("=" * 60)
    except Exception as e:
        logger.error(f"初始化认证系统时发生错误: {e}", exc_info=True)

# 3. 定义所有认证相关的路由
@auth_bp.route('/status', methods=['GET'])
def auth_status():
    """检查当前认证状态"""
    config = config_manager.APP_CONFIG
    auth_enabled = config.get(constants.CONFIG_OPTION_AUTH_ENABLED, False)
    response = {
        "auth_enabled": auth_enabled,
        "logged_in": 'user_id' in session,
        "username": session.get('username')
    }
    return jsonify(response)

@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return jsonify({"error": "缺少用户名或密码"}), 400

    try:
        with db_handler.get_db_connection(config_manager.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            user = cursor.fetchone()
    except Exception as e:
        logger.error(f"登录时数据库查询失败: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500

    if user and check_password_hash(user['password_hash'], password):
        session['user_id'] = user['id']
        session['username'] = user['username']
        logger.info(f"用户 '{user['username']}' 登录成功。")
        return jsonify({"message": "登录成功", "username": user['username']})
    
    logger.warning(f"用户 '{username}' 登录失败：用户名或密码错误。")
    return jsonify({"error": "用户名或密码错误"}), 401

@auth_bp.route('/logout', methods=['POST'])
def logout():
    username = session.get('username', '未知用户')
    session.clear()
    logger.info(f"用户 '{username}' 已注销。")
    return jsonify({"message": "注销成功"})

@auth_bp.route('/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.json
    current_password = data.get('current_password')
    new_password = data.get('new_password')

    if not current_password or not new_password or len(new_password) < 6:
        return jsonify({"error": "缺少参数或新密码长度不足6位"}), 400

    user_id = session.get('user_id')
    try:
        with db_handler.get_db_connection(config_manager.DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            user = cursor.fetchone()

            if not user or not check_password_hash(user['password_hash'], current_password):
                return jsonify({"error": "当前密码不正确"}), 403

            new_password_hash = generate_password_hash(new_password)
            cursor.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_password_hash, user_id))
            conn.commit()
    except Exception as e:
        logger.error(f"修改密码时发生数据库错误: {e}", exc_info=True)
        return jsonify({"error": "服务器内部错误"}), 500

    logger.info(f"用户 '{user['username']}' 成功修改密码。")
    return jsonify({"message": "密码修改成功"})