from config import query_one, query_all, execute, execute_returning, get_db_connection, get_db_cursor
from datetime import datetime


def get_blacklist(blacklist_id):
    return query_one("SELECT * FROM blacklist WHERE id = %s", (blacklist_id,))


def get_active_blacklist_by_phone(member_phone):
    now = datetime.now()
    return query_one("""
        SELECT * FROM blacklist
        WHERE member_phone = %s AND status = 'active'
          AND start_time <= %s AND (end_time IS NULL OR end_time > %s)
    """, (member_phone, now, now))


def is_member_blacklisted(member_phone):
    entry = get_active_blacklist_by_phone(member_phone)
    return entry is not None, entry


def list_blacklist(status=None, member_phone=None):
    sql = "SELECT * FROM blacklist WHERE 1=1"
    params = []
    if status:
        sql += " AND status = %s"
        params.append(status)
    if member_phone:
        sql += " AND member_phone = %s"
        params.append(member_phone)
    sql += " ORDER BY created_at DESC"
    return query_all(sql, tuple(params))


def create_blacklist(member_phone, reason, start_time=None, end_time=None, member_name=None):
    if not member_phone:
        return None, "请输入手机号"
    if not reason:
        return None, "请输入黑名单原因"

    existing, entry = is_member_blacklisted(member_phone)
    if existing:
        return None, f"该会员已在黑名单中（原因：{entry['reason']}）"

    if start_time and isinstance(start_time, str):
        try:
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00').replace(' ', 'T'))
        except Exception:
            try:
                start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
            except Exception:
                return None, "生效时间格式错误"
    if not start_time:
        start_time = datetime.now()

    if end_time and isinstance(end_time, str):
        try:
            end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00').replace(' ', 'T'))
        except Exception:
            try:
                end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M')
            except Exception:
                return None, "失效时间格式错误"

    if end_time and end_time <= start_time:
        return None, "失效时间必须晚于生效时间"

    no_show_count = 0
    if not member_name:
        last_reg = query_one("""
            SELECT member_name FROM registrations
            WHERE member_phone = %s
            ORDER BY registration_time DESC LIMIT 1
        """, (member_phone,))
        if last_reg:
            member_name = last_reg['member_name']

    record = execute_returning("""
        INSERT INTO blacklist (member_phone, member_name, reason, start_time, end_time, is_auto, no_show_count, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
    """, (member_phone, member_name, reason, start_time, end_time, False, no_show_count, 'active'))
    return record, None


def update_blacklist(blacklist_id, reason=None, start_time=None, end_time=None, member_name=None):
    entry = get_blacklist(blacklist_id)
    if not entry:
        return None, "黑名单记录不存在"

    fields = ["updated_at = %s"]
    params = [datetime.now()]

    if reason is not None:
        fields.append("reason = %s")
        params.append(reason)
    if member_name is not None:
        fields.append("member_name = %s")
        params.append(member_name)
    if start_time is not None:
        if isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00').replace(' ', 'T'))
            except Exception:
                try:
                    start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
                except Exception:
                    return None, "生效时间格式错误"
        fields.append("start_time = %s")
        params.append(start_time)
    if end_time is not None:
        if isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00').replace(' ', 'T'))
            except Exception:
                try:
                    end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M')
                except Exception:
                    return None, "失效时间格式错误"
        fields.append("end_time = %s")
        params.append(end_time)

    effective_start = start_time if start_time is not None else entry['start_time']
    effective_end = end_time if end_time is not None else entry['end_time']
    if effective_end and effective_end <= effective_start:
        return None, "失效时间必须晚于生效时间"

    params.append(blacklist_id)
    sql = f"UPDATE blacklist SET {', '.join(fields)} WHERE id = %s"
    result = execute(sql, tuple(params))
    if result > 0:
        return get_blacklist(blacklist_id), None
    return None, "更新失败"


def lift_blacklist(blacklist_id):
    entry = get_blacklist(blacklist_id)
    if not entry:
        return None, "黑名单记录不存在"
    if entry['status'] != 'active':
        return None, "该记录已解除"

    now = datetime.now()
    result = execute("""
        UPDATE blacklist SET status = 'lifted', end_time = %s, updated_at = %s WHERE id = %s
    """, (now, now, blacklist_id))
    if result > 0:
        return get_blacklist(blacklist_id), None
    return None, "解除失败"


def delete_blacklist(blacklist_id):
    entry = get_blacklist(blacklist_id)
    if not entry:
        return False, "黑名单记录不存在"
    result = execute("DELETE FROM blacklist WHERE id = %s", (blacklist_id,))
    return result > 0, None if result > 0 else "删除失败"


def get_no_show_threshold():
    config = query_one("SELECT value FROM system_config WHERE key = %s", ('no_show_threshold',))
    if config:
        try:
            return int(config['value'])
        except (ValueError, TypeError):
            return 3
    return 3


def update_no_show_threshold(threshold):
    try:
        threshold = int(threshold)
    except (ValueError, TypeError):
        return None, "阈值必须为整数"
    if threshold < 1:
        return None, "阈值必须大于0"

    result = execute("""
        INSERT INTO system_config (key, value, description, updated_at)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (key) DO UPDATE SET value = %s, updated_at = %s
    """, ('no_show_threshold', str(threshold), '失约次数达到该阈值自动加入限制名单',
          datetime.now(), str(threshold), datetime.now()))
    if result > 0 or result == 0:
        return threshold, None
    return None, "更新失败"


def check_and_auto_blacklist(member_phone, member_name=None):
    threshold = get_no_show_threshold()

    no_show_count = query_one("""
        SELECT COUNT(*) as cnt FROM registrations
        WHERE member_phone = %s AND status = 'no_show'
    """, (member_phone,))['cnt']

    if no_show_count < threshold:
        return None

    existing, entry = is_member_blacklisted(member_phone)
    if existing:
        return None

    if not member_name:
        last_reg = query_one("""
            SELECT member_name FROM registrations
            WHERE member_phone = %s
            ORDER BY registration_time DESC LIMIT 1
        """, (member_phone,))
        if last_reg:
            member_name = last_reg['member_name']

    from datetime import timedelta
    start_time = datetime.now()
    end_time = start_time + timedelta(days=30)

    execute_returning("""
        INSERT INTO blacklist (member_phone, member_name, reason, start_time, end_time, is_auto, no_show_count, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
    """, (member_phone, member_name,
          f"累计失约{no_show_count}次，达到阈值{threshold}次，自动限制报名",
          start_time, end_time, True, no_show_count, 'active'))


def get_blacklist_stats(store_id=None, date_from=None, date_to=None):
    where_clauses = ["1=1"]
    params = []
    if date_from:
        where_clauses.append("b.created_at >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("b.created_at <= %s")
        params.append(date_to)
    where_sql = " AND ".join(where_clauses)

    total_active = query_one("""
        SELECT COUNT(*) as cnt FROM blacklist b
        WHERE {where} AND status = 'active' AND start_time <= NOW() AND (end_time IS NULL OR end_time > NOW())
    """.format(where=where_sql), tuple(params))['cnt']

    auto_count = query_one("""
        SELECT COUNT(*) as cnt FROM blacklist b
        WHERE {where} AND is_auto = TRUE
    """.format(where=where_sql), tuple(params))['cnt']

    lifted_count = query_one("""
        SELECT COUNT(*) as cnt FROM blacklist b
        WHERE {where} AND status = 'lifted'
    """.format(where=where_sql), tuple(params))['cnt']

    return {
        'total_active': total_active,
        'auto_count': auto_count,
        'lifted_count': lifted_count,
    }


def auto_expire_blacklist():
    now = datetime.now()
    result = execute("""
        UPDATE blacklist SET status = 'lifted', updated_at = %s
        WHERE status = 'active' AND end_time IS NOT NULL AND end_time <= %s
    """, (now, now))
    return result
