import hashlib
import secrets
from datetime import datetime, timedelta


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(8)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 260000)
    return f"pbkdf2:sha256:260000${salt}${pwd_hash.hex()}"


def verify_password(password, stored_hash):
    try:
        parts = stored_hash.split('$')
        if len(parts) != 3:
            return False
        _, salt, _ = parts
        return hash_password(password, salt) == stored_hash
    except Exception:
        return False


def format_datetime(dt):
    if dt is None:
        return '-'
    return dt.strftime('%Y-%m-%d %H:%M')


def format_date(dt):
    if dt is None:
        return '-'
    return dt.strftime('%Y-%m-%d')


def format_time(dt):
    if dt is None:
        return '-'
    return dt.strftime('%H:%M')


def get_status_text(status):
    status_map = {
        'scheduled': '未开始',
        'ongoing': '进行中',
        'completed': '已结束',
        'cancelled': '已取消',
        'registered': '已报名',
        'checked_in': '已签到',
        'dropped': '已退课',
        'frozen': '已冻结',
        'no_show': '失约',
        'waitlist': '候补中',
        'promoted': '已转正',
    }
    return status_map.get(status, status)


def get_status_class(status):
    class_map = {
        'scheduled': 'bg-secondary',
        'ongoing': 'bg-primary',
        'completed': 'bg-success',
        'cancelled': 'bg-danger',
        'registered': 'bg-info',
        'checked_in': 'bg-success',
        'dropped': 'bg-warning',
        'frozen': 'bg-dark',
        'no_show': 'bg-danger',
        'waitlist': 'bg-warning',
        'promoted': 'bg-primary',
    }
    return class_map.get(status, 'bg-secondary')


def calculate_freeze_time(start_time, minutes_before):
    return start_time - timedelta(minutes=minutes_before)


def calculate_end_time(start_time, duration_minutes):
    return start_time + timedelta(minutes=duration_minutes)


def get_package_type_text(package_type):
    type_map = {
        'count': '次卡',
        'period': '周期卡',
        'single_store': '单店卡',
    }
    return type_map.get(package_type, package_type)


def get_package_status_text(status):
    status_map = {
        'active': '生效中',
        'expired': '已过期',
        'exhausted': '已用完',
        'cancelled': '已取消',
    }
    return status_map.get(status, status)


def get_package_status_class(status):
    class_map = {
        'active': 'bg-success',
        'expired': 'bg-secondary',
        'exhausted': 'bg-warning text-dark',
        'cancelled': 'bg-danger',
    }
    return class_map.get(status, 'bg-secondary')


def get_deduction_type_text(deduction_type):
    type_map = {
        'pre_deduct': '预占',
        'formal_deduct': '正式扣课',
        'return': '返还',
    }
    return type_map.get(deduction_type, deduction_type)


def get_deduction_type_class(deduction_type):
    class_map = {
        'pre_deduct': 'bg-info',
        'formal_deduct': 'bg-success',
        'return': 'bg-warning text-dark',
    }
    return class_map.get(deduction_type, 'bg-secondary')


def is_time_conflict(start1, end1, start2, end2):
    return start1 < end2 and start2 < end1
