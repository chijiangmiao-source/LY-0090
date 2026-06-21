from config import (
    query_one, query_all, execute, execute_returning, generate_code,
    get_db_connection, get_db_cursor
)
from datetime import datetime, timedelta
from utils import get_voucher_status_text, get_voucher_status_class


def get_voucher_validity_days():
    row = query_one("SELECT value FROM system_config WHERE key = 'voucher_validity_days'")
    if row:
        try:
            return int(row['value'])
        except (ValueError, TypeError):
            pass
    return 30


def get_voucher(voucher_id):
    return query_one("""
        SELECT mv.*, c.course_name as source_course_name, c.start_time as source_course_start,
               s.name as store_name, c.store_id as source_store_id,
               r2.reg_code as used_reg_code, c2.course_name as used_course_name
        FROM makeup_vouchers mv
        LEFT JOIN courses c ON mv.source_course_id = c.id
        LEFT JOIN stores s ON mv.store_id = s.id
        LEFT JOIN registrations r2 ON mv.used_registration_id = r2.id
        LEFT JOIN courses c2 ON r2.course_id = c2.id
        WHERE mv.id = %s
    """, (voucher_id,))


def get_voucher_by_code(voucher_code):
    return query_one("SELECT * FROM makeup_vouchers WHERE voucher_code = %s", (voucher_code,))


def list_vouchers(member_phone=None, status=None, store_id=None):
    sql = """
        SELECT mv.*, c.course_name as source_course_name, c.start_time as source_course_start,
               s.name as store_name,
               r2.reg_code as used_reg_code, c2.course_name as used_course_name
        FROM makeup_vouchers mv
        LEFT JOIN courses c ON mv.source_course_id = c.id
        LEFT JOIN stores s ON mv.store_id = s.id
        LEFT JOIN registrations r2 ON mv.used_registration_id = r2.id
        LEFT JOIN courses c2 ON r2.course_id = c2.id
        WHERE 1=1
    """
    params = []
    if member_phone:
        sql += " AND mv.member_phone = %s"
        params.append(member_phone)
    if status:
        sql += " AND mv.status = %s"
        params.append(status)
    if store_id:
        sql += " AND (mv.store_id = %s OR mv.store_id IS NULL)"
        params.append(store_id)
    sql += " ORDER BY mv.generated_at DESC"
    return query_all(sql, tuple(params))


def select_available_voucher(member_phone, store_id=None, cur=None):
    now = datetime.now()
    sql = """
        SELECT mv.* FROM makeup_vouchers mv
        WHERE mv.member_phone = %s
          AND mv.status = 'unused'
          AND mv.generated_at <= %s
          AND mv.expiry_time > %s
    """
    params = [member_phone, now, now]
    if store_id:
        sql += " AND (mv.store_id IS NULL OR mv.store_id = %s)"
        params.append(store_id)
    sql += " ORDER BY mv.expiry_time ASC LIMIT 1"
    if cur:
        sql += " FOR UPDATE"
        cur.execute(sql, tuple(params))
        return cur.fetchone()
    return query_one(sql, tuple(params))


def apply_leave(registration_id, reason=None):
    from registrations import get_registration
    import courses as course_module
    import packages as package_module

    reg = get_registration(registration_id)
    if not reg:
        return None, None, "报名记录不存在"
    if reg['status'] != 'registered':
        return None, None, "仅已报名状态可申请请假保课"
    if reg['is_waitlist']:
        return None, None, "候补会员不可申请请假保课"

    course = course_module.get_course(reg['course_id'])
    if not course:
        return None, None, "课程不存在"

    now = datetime.now()
    if now >= course['freeze_time']:
        return None, None, "课程已进入冻结期，不可申请请假保课"

    existing_leave = query_one("""
        SELECT id FROM leave_requests
        WHERE registration_id = %s AND status = 'approved'
    """, (registration_id,))
    if existing_leave:
        return None, None, "该报名已申请过请假保课"

    with get_db_connection() as conn:
        cur = get_db_cursor(conn)

        cur.execute("""
            UPDATE registrations
            SET status = 'leave', updated_at = %s
            WHERE id = %s AND status = 'registered'
            RETURNING *
        """, (now, registration_id))
        updated_reg = cur.fetchone()
        if not updated_reg:
            conn.rollback()
            return None, None, "请假保课申请失败，报名状态可能已变更"

        pre_deduction = query_one("""
            SELECT cd.*, mp.package_name FROM course_deductions cd
            LEFT JOIN member_packages mp ON cd.package_id = mp.id
            WHERE cd.registration_id = %s AND cd.deduction_type = 'pre_deduct'
            ORDER BY cd.created_at DESC LIMIT 1
        """, (registration_id,))
        if pre_deduction:
            package_module.return_pre_deduct(registration_id, pre_deduction['package_id'], cur, "请假保课返还预占课次")

        validity_days = get_voucher_validity_days()
        expiry_time = now + timedelta(days=validity_days)
        voucher_code = generate_code('VC')

        cur.execute("""
            INSERT INTO makeup_vouchers (voucher_code, source_course_id, source_registration_id,
                                          member_name, member_phone, generated_at, expiry_time,
                                          status, store_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
        """, (voucher_code, reg['course_id'], registration_id,
              reg['member_name'], reg['member_phone'], now, expiry_time,
              'unused', course['store_id']))
        voucher = cur.fetchone()

        cur.execute("""
            INSERT INTO leave_requests (registration_id, course_id, member_phone, member_name,
                                         reason, leave_time, status, voucher_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
        """, (registration_id, reg['course_id'], reg['member_phone'], reg['member_name'],
              reason, now, 'approved', voucher['id']))
        leave_req = cur.fetchone()

        cur.execute("""
            SELECT COUNT(*) as cnt FROM registrations
            WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
        """, (reg['course_id'],))
        current_waitlist = cur.fetchone()['cnt']
        cur.execute("UPDATE courses SET waitlist_count = %s WHERE id = %s",
                    (current_waitlist, reg['course_id']))

        from registrations import _promote_next_waitlist_internal
        promoted_info = _promote_next_waitlist_internal(cur, reg['course_id'], now, registration_id)

        conn.commit()

        msg = f"请假保课成功，已生成补课券 {voucher_code}（有效期至{expiry_time.strftime('%Y-%m-%d %H:%M')}）"
        if promoted_info:
            msg += f"，候补会员{promoted_info['member_name']}已自动转正"

        return dict(voucher), dict(leave_req), msg


def use_voucher_for_registration(voucher_id, registration_id, cur=None):
    now = datetime.now()

    def _do_use(cursor):
        cursor.execute("""
            SELECT * FROM makeup_vouchers WHERE id = %s FOR UPDATE
        """, (voucher_id,))
        voucher = cursor.fetchone()
        if not voucher or voucher['status'] != 'unused':
            return None, "补课券不可用"
        if voucher['expiry_time'] <= now:
            return None, "补课券已过期"

        cursor.execute("""
            UPDATE makeup_vouchers
            SET status = 'used', used_registration_id = %s, used_at = %s, updated_at = %s
            WHERE id = %s AND status = 'unused'
            RETURNING *
        """, (registration_id, now, now, voucher_id))
        updated = cursor.fetchone()
        if not updated:
            return None, "补课券使用失败"

        cursor.execute("""
            INSERT INTO course_deductions (registration_id, voucher_id, deduction_type, count, created_at, notes)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
        """, (registration_id, voucher_id, 'voucher_deduct', 1, now,
              f"补课券抵扣，券编号: {voucher['voucher_code']}，来源课程ID: {voucher['source_course_id']}"))

        deduction = cursor.fetchone()
        return dict(deduction), None

    if cur:
        return _do_use(cur)
    with get_db_connection() as conn:
        c = get_db_cursor(conn)
        return _do_use(c)


def void_voucher(voucher_id, reason=None):
    voucher = get_voucher(voucher_id)
    if not voucher:
        return None, "补课券不存在"
    if voucher['status'] != 'unused':
        return None, "仅未使用的补课券可作废"

    now = datetime.now()
    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        cur.execute("""
            UPDATE makeup_vouchers
            SET status = 'voided', voided_at = %s, void_reason = %s, updated_at = %s
            WHERE id = %s AND status = 'unused'
            RETURNING *
        """, (now, reason, now, voucher_id))
        updated = cur.fetchone()
        if not updated:
            conn.rollback()
            return None, "作废失败"
        conn.commit()
    return get_voucher(voucher_id), None


def auto_expire_vouchers():
    now = datetime.now()
    result = execute("""
        UPDATE makeup_vouchers SET status = 'expired', updated_at = %s
        WHERE status = 'unused' AND expiry_time <= %s
    """, (now, now))
    return result


def get_member_vouchers_summary(member_phone):
    vouchers = list_vouchers(member_phone=member_phone, status='unused')
    now = datetime.now()
    valid_vouchers = []
    for v in vouchers:
        if v['expiry_time'] > now:
            valid_vouchers.append(v)
    return valid_vouchers


def get_voucher_stats(store_id=None, date_from=None, date_to=None):
    where_clauses = ["1=1"]
    params = []
    if date_from:
        where_clauses.append("mv.generated_at >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("mv.generated_at <= %s")
        params.append(date_to)

    store_filter_sql = ""
    store_params = []
    if store_id:
        store_filter_sql = " AND (mv.store_id = %s OR mv.store_id IS NULL)"
        store_params = [store_id]

    where_sql = " AND ".join(where_clauses)
    all_params = tuple(params + store_params)

    total_generated = query_one("""
        SELECT COUNT(*) as cnt FROM makeup_vouchers mv
        WHERE {where} {store_filter}
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_unused = query_one("""
        SELECT COUNT(*) as cnt FROM makeup_vouchers mv
        WHERE {where} {store_filter} AND mv.status = 'unused'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_used = query_one("""
        SELECT COUNT(*) as cnt FROM makeup_vouchers mv
        WHERE {where} {store_filter} AND mv.status = 'used'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_expired = query_one("""
        SELECT COUNT(*) as cnt FROM makeup_vouchers mv
        WHERE {where} {store_filter} AND mv.status = 'expired'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    total_voided = query_one("""
        SELECT COUNT(*) as cnt FROM makeup_vouchers mv
        WHERE {where} {store_filter} AND mv.status = 'voided'
    """.format(where=where_sql, store_filter=store_filter_sql), all_params)['cnt']

    voucher_redemption_rate = 0
    if total_generated > 0:
        voucher_redemption_rate = round((total_used / total_generated) * 100, 1)

    return {
        'total_generated': total_generated,
        'total_unused': total_unused,
        'total_used': total_used,
        'total_expired': total_expired,
        'total_voided': total_voided,
        'voucher_redemption_rate': voucher_redemption_rate,
    }


def get_leave_requests_by_course(course_id):
    return query_all("""
        SELECT lr.*, mv.voucher_code, mv.expiry_time as voucher_expiry, mv.status as voucher_status
        FROM leave_requests lr
        LEFT JOIN makeup_vouchers mv ON lr.voucher_id = mv.id
        WHERE lr.course_id = %s
        ORDER BY lr.leave_time DESC
    """, (course_id,))


def get_leave_requests_by_phone(member_phone):
    return query_all("""
        SELECT lr.*, c.course_name, c.start_time as course_start,
               mv.voucher_code, mv.expiry_time as voucher_expiry, mv.status as voucher_status
        FROM leave_requests lr
        LEFT JOIN courses c ON lr.course_id = c.id
        LEFT JOIN makeup_vouchers mv ON lr.voucher_id = mv.id
        WHERE lr.member_phone = %s
        ORDER BY lr.leave_time DESC
    """, (member_phone,))
