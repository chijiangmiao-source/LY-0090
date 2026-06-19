from bottle import request, redirect, abort
from functools import wraps
from config import query_one, query_all, execute, execute_returning, SECRET_KEY
from utils import hash_password, verify_password
from datetime import datetime


def get_current_user():
    session = request.environ.get('beaker.session')
    if session and 'user_id' in session:
        try:
            user = query_one("SELECT * FROM users WHERE id = %s", (session['user_id'],))
            return user
        except Exception:
            return None
    return None


def require_login(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.headers.get('HX-Request'):
                from bottle import response
                response.status = 401
                return '<script>window.location.href="/login";</script>'
            redirect('/login')
        return f(*args, **kwargs)
    return wrapper


def login_user(username, password):
    try:
        user = query_one("SELECT * FROM users WHERE username = %s", (username,))
    except Exception:
        return None, "数据库未就绪，请先检查 PostgreSQL 连接配置"
    if not user:
        return None, "用户不存在"
    if not verify_password(password, user['password_hash']):
        return None, "密码错误"
    execute("UPDATE users SET last_login = %s WHERE id = %s", (datetime.now(), user['id']))
    session = request.environ.get('beaker.session')
    if session is None:
        return None, "会话初始化失败，请重试"
    session['user_id'] = user['id']
    session['username'] = user['username']
    session['real_name'] = user['real_name']
    if hasattr(session, 'save'):
        session.save()
    return user, None


def logout_user():
    session = request.environ.get('beaker.session')
    if session:
        session.delete()


def create_user(username, password, real_name, role='admin', store_id=None):
    if query_one("SELECT id FROM users WHERE username = %s", (username,)):
        return None, "用户名已存在"
    pwd_hash = hash_password(password)
    user = execute_returning(
        "INSERT INTO users (username, password_hash, real_name, role, store_id) VALUES (%s, %s, %s, %s, %s) RETURNING *",
        (username, pwd_hash, real_name, role, store_id)
    )
    return user, None


def list_users():
    return query_all("""
        SELECT u.*, s.name as store_name 
        FROM users u LEFT JOIN stores s ON u.store_id = s.id 
        ORDER BY u.id
    """)


def update_user(user_id, real_name=None, role=None, store_id=None, password=None):
    fields = []
    params = []
    if real_name is not None:
        fields.append("real_name = %s")
        params.append(real_name)
    if role is not None:
        fields.append("role = %s")
        params.append(role)
    if store_id is not None:
        fields.append("store_id = %s")
        params.append(store_id)
    if password is not None:
        fields.append("password_hash = %s")
        params.append(hash_password(password))
    if not fields:
        return False
    params.append(user_id)
    sql = f"UPDATE users SET {', '.join(fields)} WHERE id = %s"
    return execute(sql, tuple(params)) > 0


def delete_user(user_id):
    return execute("DELETE FROM users WHERE id = %s", (user_id,)) > 0
