import re
from config import (
    query_one, query_all, execute, execute_returning, generate_code,
    get_db_connection, get_db_cursor
)
from datetime import datetime


def get_package(package_id):
    return query_one("""
        SELECT mp.*, s.name as store_name
        FROM member_packages mp
        LEFT JOIN stores s ON mp.store_id = s.id
        WHERE mp.id = %s
    """, (package_id,))


def get_package_by_code(package_code):
    return query_one("SELECT * FROM member_packages WHERE package_code = %s", (package_code,))


def list_packages(member_phone=None, status=None, package_type=None, store_id=None):
    sql = """
        SELECT mp.*, s.name as store_name
        FROM member_packages mp
        LEFT JOIN stores s ON mp.store_id = s.id
        WHERE 1=1
    """
    params = []
    if member_phone:
        sql += " AND mp.member_phone = %s"
        params.append(member_phone)
    if status:
        sql += " AND mp.status = %s"
        params.append(status)
    if package_type:
        sql += " AND mp.package_type = %s"
        params.append(package_type)
    if store_id:
        sql += " AND mp.store_id = %s"
        params.append(store_id)
    sql += " ORDER BY mp.end_time ASC, mp.created_at DESC"
    return query_all(sql, tuple(params))


def create_package(member_phone, package_name, package_type, total_count,
                   start_time=None, end_time=None, store_id=None, member_name=None):
    if not member_phone:
        return None, "请输入手机号"
    if not re.match(r'^1\d{10}$', member_phone):
        return None, "请输入有效的11位手机号"
    if not package_name:
        return None, "请输入套餐名称"
    if not package_type:
        return None, "请选择套餐类型"
    if package_type not in ('count', 'period', 'single_store'):
        return None, "无效的套餐类型"

    if package_type != 'period' and (total_count is None or int(total_count) <= 0):
        return None, "总次数必须大于0"

    if package_type == 'period':
        total_count_int = 99999
    else:
        total_count_int = int(total_count)

    if not member_name:
        last_reg = query_one("""
            SELECT member_name FROM registrations
            WHERE member_phone = %s
            ORDER BY registration_time DESC LIMIT 1
        """, (member_phone,))
        if last_reg:
            member_name = last_reg['member_name']

    if package_type == 'single_store' and not store_id:
        return None, "单店卡必须选择适用门店"

    if package_type != 'single_store':
        store_id = None

    now = datetime.now()
    if start_time and isinstance(start_time, str):
        try:
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00').replace(' ', 'T'))
        except Exception:
            try:
                start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
            except Exception:
                return None, "生效时间格式错误"
    if not start_time:
        start_time = now

    if end_time and isinstance(end_time, str):
        try:
            end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00').replace(' ', 'T'))
        except Exception:
            try:
                end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M')
            except Exception:
                return None, "失效时间格式错误"
    if not end_time:
        return None, "请输入失效时间"
    if end_time <= start_time:
        return None, "失效时间必须晚于生效时间"

    total_count_int = int(total_count)
    package_code = generate_code('PKG')
    record = execute_returning("""
        INSERT INTO member_packages (package_code, member_phone, member_name, package_name,
                                      package_type, store_id, total_count, remaining_count,
                                      reserved_count, start_time, end_time, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
    """, (package_code, member_phone, member_name, package_name,
          package_type, store_id, total_count_int, total_count_int,
          0, start_time, end_time, 'active'))
    return record, None


def update_package(package_id, package_name=None, store_id=None,
                   start_time=None, end_time=None, status=None):
    pkg = get_package(package_id)
    if not pkg:
        return None, "套餐不存在"

    fields = ["updated_at = %s"]
    params = [datetime.now()]

    if package_name is not None:
        fields.append("package_name = %s")
        params.append(package_name)

    if store_id is not None:
        if pkg['package_type'] == 'single_store' and not store_id:
            return None, "单店卡必须选择适用门店"
        if pkg['package_type'] != 'single_store':
            store_id = None
        fields.append("store_id = %s")
        params.append(store_id)

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

    effective_start = start_time if start_time is not None else pkg['start_time']
    effective_end = end_time if end_time is not None else pkg['end_time']
    if effective_end and effective_end <= effective_start:
        return None, "失效时间必须晚于生效时间"

    if status is not None:
        if status not in ('active', 'expired', 'exhausted', 'cancelled'):
            return None, "无效的套餐状态"
        fields.append("status = %s")
        params.append(status)

    params.append(package_id)
    sql = f"UPDATE member_packages SET {', '.join(fields)} WHERE id = %s"
    result = execute(sql, tuple(params))
    if result > 0:
        return get_package(package_id), None
    return None, "更新失败"


def delete_package(package_id):
    pkg = get_package(package_id)
    if not pkg:
        return False, "套餐不存在"
    deduction_count = query_one(
        "SELECT COUNT(*) as cnt FROM course_deductions WHERE package_id = %s",
        (package_id,)
    )['cnt']
    if deduction_count > 0:
        return False, f"该套餐已有{deduction_count}条扣课记录，无法删除"
    result = execute("DELETE FROM member_packages WHERE id = %s", (package_id,))
    return result > 0, None if result > 0 else "删除失败"


def select_available_package(member_phone, store_id=None, cur=None):
    now = datetime.now()
    sql = """
        SELECT mp.* FROM member_packages mp
        WHERE mp.member_phone = %s
          AND mp.status = 'active'
          AND mp.start_time <= %s
          AND mp.end_time > %s
          AND (mp.package_type = 'period' OR (mp.remaining_count - mp.reserved_count) > 0)
    """
    params = [member_phone, now, now]

    if store_id:
        sql += " AND (mp.package_type != 'single_store' OR mp.store_id = %s)"
        params.append(store_id)

    if cur:
        sql += " ORDER BY mp.end_time ASC, mp.remaining_count ASC LIMIT 1 FOR UPDATE"
        cur.execute(sql, tuple(params))
        return cur.fetchone()
    sql += " ORDER BY mp.end_time ASC, mp.remaining_count ASC LIMIT 1"
    return query_one(sql, tuple(params))


def pre_deduct(registration_id, package_id, cur=None):
    now = datetime.now()

    def _do_pre_deduct(cursor):
        cursor.execute("""
            SELECT * FROM member_packages WHERE id = %s FOR UPDATE
        """, (package_id,))
        pkg = cursor.fetchone()
        if not pkg or pkg['status'] != 'active':
            return None, "套餐不可用"

        if pkg['package_type'] != 'period':
            available = pkg['remaining_count'] - pkg['reserved_count']
            if available <= 0:
                return None, "套餐剩余可用次数不足"
            cursor.execute("""
                UPDATE member_packages
                SET reserved_count = reserved_count + 1, updated_at = %s
                WHERE id = %s
            """, (now, package_id))

        cursor.execute("""
            INSERT INTO course_deductions (registration_id, package_id, deduction_type, count, created_at, notes)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
        """, (registration_id, package_id, 'pre_deduct', 1, now,
              f"报名预占课次，套餐: {pkg['package_name']}（{get_package_type_text(pkg['package_type'])}）"))
        deduction = cursor.fetchone()
        return dict(deduction), None

    if cur:
        return _do_pre_deduct(cur)
    with get_db_connection() as conn:
        c = get_db_cursor(conn)
        result = _do_pre_deduct(c)
        return result


def formal_deduct(registration_id, package_id, cur=None):
    now = datetime.now()

    def _do_formal_deduct(cursor):
        cursor.execute("""
            SELECT * FROM member_packages WHERE id = %s
        """, (package_id,))
        pkg = cursor.fetchone()
        if not pkg:
            return None, "套餐不存在"

        if pkg['package_type'] != 'period':
            cursor.execute("""
                UPDATE member_packages
                SET remaining_count = remaining_count - 1,
                    reserved_count = reserved_count - 1,
                    updated_at = %s
                WHERE id = %s AND remaining_count > 0 AND reserved_count > 0
            """, (now, package_id))
            if cursor.rowcount == 0:
                return None, "扣课失败，套餐状态异常"

            cursor.execute("""
                SELECT * FROM member_packages WHERE id = %s
            """, (package_id,))
            pkg = cursor.fetchone()

            if pkg and pkg['remaining_count'] - pkg['reserved_count'] <= 0 and pkg['reserved_count'] <= 0:
                cursor.execute("""
                    UPDATE member_packages SET status = 'exhausted', updated_at = %s WHERE id = %s
                """, (now, package_id))
        else:
            cursor.execute("""
                UPDATE member_packages
                SET reserved_count = reserved_count - 1,
                    updated_at = %s
                WHERE id = %s AND reserved_count > 0
            """, (now, package_id))

        type_text = get_package_type_text(pkg['package_type']) if pkg else ''
        cursor.execute("""
            INSERT INTO course_deductions (registration_id, package_id, deduction_type, count, created_at, notes)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
        """, (registration_id, package_id, 'formal_deduct', 1, now,
              f"签到正式扣课，套餐: {pkg['package_name'] if pkg else ''}（{type_text}）"))

        deduction = cursor.fetchone()
        return dict(deduction), None

    if cur:
        return _do_formal_deduct(cur)
    with get_db_connection() as conn:
        c = get_db_cursor(conn)
        result = _do_formal_deduct(c)
        return result


def return_pre_deduct(registration_id, package_id, cur=None, reason="正常退课返还预占课次"):
    now = datetime.now()

    def _do_return(cursor):
        cursor.execute("""
            SELECT * FROM member_packages WHERE id = %s
        """, (package_id,))
        pkg = cursor.fetchone()
        if not pkg:
            return None, "套餐不存在"

        if pkg['package_type'] != 'period':
            cursor.execute("""
                UPDATE member_packages
                SET reserved_count = reserved_count - 1,
                    updated_at = %s
                WHERE id = %s AND reserved_count > 0
            """, (now, package_id))
            if cursor.rowcount == 0:
                return None, "返还失败，套餐状态异常"

            if pkg and pkg['status'] == 'exhausted' and (pkg['remaining_count'] - pkg['reserved_count']) > 0:
                cursor.execute("""
                    UPDATE member_packages SET status = 'active', updated_at = %s WHERE id = %s
                """, (now, package_id))
        else:
            cursor.execute("""
                UPDATE member_packages
                SET reserved_count = reserved_count - 1,
                    updated_at = %s
                WHERE id = %s AND reserved_count > 0
            """, (now, package_id))
            if cursor.rowcount == 0:
                return None, "返还失败，套餐状态异常"

        type_text = get_package_type_text(pkg['package_type'])

        cursor.execute("""
            INSERT INTO course_deductions (registration_id, package_id, deduction_type, count, created_at, notes)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
        """, (registration_id, package_id, 'return', 1, now,
              f"{reason}，套餐: {pkg['package_name'] if pkg else ''}（{type_text}）"))

        if pkg and pkg['package_type'] != 'period' and pkg['status'] == 'exhausted' and (pkg['remaining_count'] - pkg['reserved_count']) > 0:
            cursor.execute("""
                UPDATE member_packages SET status = 'active', updated_at = %s WHERE id = %s
            """, (now, package_id))

        deduction = cursor.fetchone()
        return dict(deduction), None

    if cur:
        return _do_return(cursor)
    with get_db_connection() as conn:
        c = get_db_cursor(conn)
        result = _do_return(c)
        return result


def get_deductions_by_registration(registration_id):
    return query_all("""
        SELECT cd.*, mp.package_name, mp.package_code, mp.package_type
        FROM course_deductions cd
        LEFT JOIN member_packages mp ON cd.package_id = mp.id
        WHERE cd.registration_id = %s
        ORDER BY cd.created_at
    """, (registration_id,))


def get_deductions_by_package(package_id):
    return query_all("""
        SELECT cd.*, r.member_name, r.member_phone, r.status as reg_status,
               c.course_name, c.start_time as course_start_time
        FROM course_deductions cd
        LEFT JOIN registrations r ON cd.registration_id = r.id
        LEFT JOIN courses c ON r.course_id = c.id
        WHERE cd.package_id = %s
        ORDER BY cd.created_at DESC
    """, (package_id,))


def get_member_packages_summary(member_phone):
    packages = list_packages(member_phone=member_phone, status='active')
    now = datetime.now()
    active_packages = []
    for pkg in packages:
        if pkg['start_time'] <= now < pkg['end_time']:
            active_packages.append(pkg)
    return active_packages


def get_package_stats(store_id=None, date_from=None, date_to=None):
    where_clauses = ["1=1"]
    params = []
    if date_from:
        where_clauses.append("mp.created_at >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("mp.created_at <= %s")
        params.append(date_to)

    store_filter_sql = ""
    store_params = []
    if store_id:
        store_filter_sql = " AND mp.store_id = %s"
        store_params = [store_id]

    where_sql = " AND ".join(where_clauses)
    all_params = tuple(params + store_params)

    total_active = query_one("""
        SELECT COUNT(*) as cnt FROM member_packages mp
        WHERE {where} {store_filter} AND status = 'active'
          AND start_time <= NOW() AND end_time > NOW()
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_deductions = query_one("""
        SELECT COUNT(*) as cnt FROM course_deductions cd
        JOIN member_packages mp ON cd.package_id = mp.id
        WHERE {where} {store_filter} AND cd.deduction_type = 'formal_deduct'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_pre_deducts = query_one("""
        SELECT COUNT(*) as cnt FROM course_deductions cd
        JOIN member_packages mp ON cd.package_id = mp.id
        WHERE {where} {store_filter} AND cd.deduction_type = 'pre_deduct'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_returns = query_one("""
        SELECT COUNT(*) as cnt FROM course_deductions cd
        JOIN member_packages mp ON cd.package_id = mp.id
        WHERE {where} {store_filter} AND cd.deduction_type = 'return'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    abnormal_count = query_one("""
        SELECT COUNT(*) as cnt FROM course_deductions cd
        JOIN member_packages mp ON cd.package_id = mp.id
        JOIN registrations r ON cd.registration_id = r.id
        WHERE {where} {store_filter} AND cd.deduction_type = 'formal_deduct'
          AND r.status IN ('frozen', 'no_show')
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_package_count = query_one("""
        SELECT COUNT(*) as cnt FROM member_packages mp
        WHERE {where} {store_filter}
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_remaining = query_one("""
        SELECT COALESCE(SUM(remaining_count), 0) as sum FROM member_packages mp
        WHERE {where} {store_filter} AND status = 'active' AND package_type != 'period'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['sum']

    total_reserved = query_one("""
        SELECT COALESCE(SUM(reserved_count), 0) as sum FROM member_packages mp
        WHERE {where} {store_filter} AND status = 'active'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['sum']

    total_total = query_one("""
        SELECT COALESCE(SUM(total_count), 0) as sum FROM member_packages mp
        WHERE {where} {store_filter} AND package_type != 'period'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['sum']

    period_active_count = query_one("""
        SELECT COUNT(*) as cnt FROM member_packages mp
        WHERE {where} {store_filter} AND status = 'active' AND package_type = 'period'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    count_active_count = query_one("""
        SELECT COUNT(*) as cnt FROM member_packages mp
        WHERE {where} {store_filter} AND status = 'active' AND package_type != 'period'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    consumption_rate = 0
    if total_total > 0:
        consumption_rate = round(((total_total - total_remaining) / total_total) * 100, 1)

    return {
        'total_active': total_active,
        'total_deductions': total_deductions,
        'total_pre_deducts': total_pre_deducts,
        'total_returns': total_returns,
        'abnormal_count': abnormal_count,
        'total_package_count': total_package_count,
        'total_remaining': total_remaining,
        'total_reserved': total_reserved,
        'total_total': total_total,
        'consumption_rate': consumption_rate,
        'period_active_count': period_active_count,
        'count_active_count': count_active_count,
    }


def auto_expire_packages():
    now = datetime.now()
    result = execute("""
        UPDATE member_packages SET status = 'expired', updated_at = %s
        WHERE status = 'active' AND end_time <= %s
    """, (now, now))
    return result


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
        'voucher_deduct': '补课券抵扣',
    }
    return type_map.get(deduction_type, deduction_type)


def get_deduction_type_class(deduction_type):
    class_map = {
        'pre_deduct': 'bg-info',
        'formal_deduct': 'bg-success',
        'return': 'bg-warning text-dark',
        'voucher_deduct': 'bg-purple',
    }
    return class_map.get(deduction_type, 'bg-secondary')
