import re
from config import (
    query_one, query_all, execute, execute_returning, generate_code,
    get_db_connection, get_db_cursor, CLASS_DURATION_MINUTES
)
from utils import is_time_conflict
from datetime import datetime
import courses as course_module
import blacklist as blacklist_module
import packages as package_module


def get_registration(reg_id):
    return query_one("""
        SELECT r.*, c.course_name, c.course_code, c.start_time, c.end_time, c.max_students,
               c.status as course_status, c.freeze_time, s.name as store_name, cl.name as classroom_name
        FROM registrations r
        LEFT JOIN courses c ON r.course_id = c.id
        LEFT JOIN stores s ON c.store_id = s.id
        LEFT JOIN classrooms cl ON c.classroom_id = cl.id
        WHERE r.id = %s
    """, (reg_id,))


def get_registration_by_code(reg_code):
    return query_one("""
        SELECT r.*, c.course_name, c.course_code, c.start_time, c.end_time, c.max_students,
               c.status as course_status, c.freeze_time
        FROM registrations r
        LEFT JOIN courses c ON r.course_id = c.id
        WHERE r.reg_code = %s
    """, (reg_code,))


def list_registrations(course_id=None, member_phone=None, status=None, date_from=None, date_to=None):
    sql = """
        SELECT r.*, c.course_name, c.course_code, c.start_time, c.end_time,
               c.status as course_status, s.name as store_name
        FROM registrations r
        LEFT JOIN courses c ON r.course_id = c.id
        LEFT JOIN stores s ON c.store_id = s.id
        WHERE 1=1
    """
    params = []
    if course_id:
        sql += " AND r.course_id = %s"
        params.append(course_id)
    if member_phone:
        sql += " AND r.member_phone = %s"
        params.append(member_phone)
    if status:
        sql += " AND r.status = %s"
        params.append(status)
    if date_from:
        sql += " AND r.registration_time >= %s"
        params.append(date_from)
    if date_to:
        sql += " AND r.registration_time <= %s"
        params.append(date_to)
    sql += " ORDER BY r.registration_time DESC"
    return query_all(sql, tuple(params))


def check_member_time_conflict(member_phone, course_start, course_end, exclude_course_id=None):
    sql = """
        SELECT DISTINCT c.id, c.course_name, c.start_time, c.end_time
        FROM registrations r
        JOIN courses c ON r.course_id = c.id
        WHERE r.member_phone = %s
          AND r.status NOT IN ('dropped', 'frozen')
          AND r.is_waitlist = FALSE
          AND c.status != 'cancelled'
    """
    params = [member_phone]
    if exclude_course_id:
        sql += " AND c.id != %s"
        params.append(exclude_course_id)
    existing_courses = query_all(sql, tuple(params))
    for ec in existing_courses:
        if is_time_conflict(course_start, course_end, ec['start_time'], ec['end_time']):
            return ec
    return None


def check_member_already_registered(course_id, member_phone):
    return query_one("""
        SELECT * FROM registrations
        WHERE course_id = %s AND member_phone = %s
          AND status NOT IN ('dropped')
    """, (course_id, member_phone))


def create_registration(course_id, member_name, member_phone):
    if not course_id:
        return None, "请选择课程"
    if not member_name:
        return None, "请输入会员姓名"
    if not member_phone:
        return None, "请输入手机号"
    if not re.match(r'^1\d{10}$', member_phone):
        return None, "请输入有效的11位手机号"

    course = course_module.get_course(course_id)
    if not course:
        return None, "课程不存在"
    if course['status'] == 'cancelled':
        return None, "课程已取消"
    if course['status'] == 'completed':
        return None, "课程已结束"

    now = datetime.now()

    blacklisted, bl_entry = blacklist_module.is_member_blacklisted(member_phone)
    if blacklisted:
        end_info = f"，限制至{bl_entry['end_time'].strftime('%Y-%m-%d %H:%M')}" if bl_entry['end_time'] else "，限制未设结束时间"
        return None, f"该会员在黑名单中（原因：{bl_entry['reason']}{end_info}）"

    existing = check_member_already_registered(course_id, member_phone)
    if existing:
        status_text = "候补" if existing['is_waitlist'] else "报名"
        return None, f"该会员已{status_text}此课程"

    conflict = check_member_time_conflict(member_phone, course['start_time'], course['end_time'], course_id)
    if conflict:
        return None, f"该会员在同时段已报名：{conflict['course_name']}"

    with get_db_connection() as conn:
        cur = get_db_cursor(conn)

        cur.execute("""
            SELECT COUNT(*) as cnt FROM registrations
            WHERE course_id = %s AND is_waitlist = FALSE AND status NOT IN ('dropped', 'frozen')
            FOR UPDATE
        """, (course_id,))
        normal_count = cur.fetchone()['cnt']

        cur.execute("""
            SELECT COUNT(*) as cnt FROM registrations
            WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
        """, (course_id,))
        waitlist_count = cur.fetchone()['cnt']

        reg_code = generate_code('REG')
        is_waitlist = normal_count >= course['max_students']

        if is_waitlist:
            waitlist_order = waitlist_count + 1
            cur.execute("""
                INSERT INTO registrations (reg_code, course_id, member_name, member_phone,
                                          registration_time, status, is_waitlist, waitlist_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (reg_code, course_id, member_name, member_phone, now, 'waitlist', True, waitlist_order))
            reg = cur.fetchone()

            cur.execute("""
                INSERT INTO waitlist_history (registration_id, course_id, action, new_waitlist_order, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (reg['id'], course_id, 'join_waitlist', waitlist_order, '加入候补队列'))

            cur.execute("""
                UPDATE courses SET waitlist_count = %s, updated_at = %s WHERE id = %s
            """, (waitlist_count + 1, now, course_id))
        else:
            cur.execute("""
                INSERT INTO registrations (reg_code, course_id, member_name, member_phone,
                                          registration_time, status, is_waitlist)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
            """, (reg_code, course_id, member_name, member_phone, now, 'registered', False))
            reg = cur.fetchone()

            pkg = package_module.select_available_package(member_phone, course['store_id'], cur)
            pkg_name = None
            if pkg:
                deduction, ded_err = package_module.pre_deduct(reg['id'], pkg['id'], cur)
                if ded_err:
                    conn.rollback()
                    return None, f"报名成功但套餐预占失败：{ded_err}"
                pkg_name = pkg.get('package_name', '')

        conn.commit()
        msg = "候补成功" if is_waitlist else "报名成功"
        if not is_waitlist:
            if pkg_name:
                msg += f"（已从套餐「{pkg_name}」预占1次）"
            else:
                msg += "（该会员暂无可用套餐）"
        return dict(reg), msg


def checkin_registration(reg_id):
    reg = get_registration(reg_id)
    if not reg:
        return None, "报名记录不存在"
    if reg['is_waitlist']:
        return None, "候补会员不能签到，请先转正"
    if reg['status'] == 'checked_in':
        return None, "该会员已签到"
    if reg['status'] == 'dropped':
        return None, "该会员已退课"
    if reg['status'] == 'frozen':
        return None, "该报名已冻结"

    blacklisted, bl_entry = blacklist_module.is_member_blacklisted(reg['member_phone'])
    if blacklisted:
        end_info = f"，限制至{bl_entry['end_time'].strftime('%Y-%m-%d %H:%M')}" if bl_entry['end_time'] else ""
        return None, f"该会员在黑名单中，无法签到（原因：{bl_entry['reason']}{end_info}）"

    course = course_module.get_course(reg['course_id'])
    now = datetime.now()

    if now < course['start_time']:
        return None, "课程尚未开始，暂不能签到"
    if now > course['end_time']:
        return None, "课程已结束，无法签到"

    now = datetime.now()
    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        cur.execute("""
            UPDATE registrations SET status = %s, checkin_time = %s, updated_at = %s
            WHERE id = %s AND status NOT IN ('checked_in', 'dropped', 'frozen')
            RETURNING *
        """, ('checked_in', now, now, reg_id))
        updated = cur.fetchone()
        if not updated:
            conn.rollback()
            return None, "签到失败"

        pre_deduction = query_one("""
            SELECT cd.*, mp.package_name FROM course_deductions cd
            LEFT JOIN member_packages mp ON cd.package_id = mp.id
            WHERE cd.registration_id = %s AND cd.deduction_type = 'pre_deduct'
            ORDER BY cd.created_at DESC LIMIT 1
        """, (reg_id,))
        pkg_info = ""
        if pre_deduction:
            _, ded_err = package_module.formal_deduct(reg_id, pre_deduction['package_id'], cur)
            if not ded_err:
                pkg_info = f"（已从套餐「{pre_deduction['package_name'] or ''}」正式扣课）"
            else:
                pkg_info = f"（正式扣课失败：{ded_err}）"

        conn.commit()
        return get_registration(reg_id), f"签到成功{pkg_info}"


def checkin_by_phone(course_id, member_phone):
    if not member_phone or not re.match(r'^1\d{10}$', member_phone):
        return None, "请输入有效的11位手机号"
    reg = query_one("""
        SELECT * FROM registrations
        WHERE course_id = %s AND member_phone = %s AND status NOT IN ('dropped')
        ORDER BY is_waitlist ASC, registration_time ASC
        LIMIT 1
    """, (course_id, member_phone))
    if not reg:
        return None, "未找到该会员的报名记录"
    return checkin_registration(reg['id'])


def dropout_registration(reg_id):
    reg = get_registration(reg_id)
    if not reg:
        return None, "报名记录不存在"
    if reg['status'] == 'dropped':
        return None, "该会员已退课"
    if reg['status'] == 'checked_in':
        return None, "已签到会员不能退课"

    course = course_module.get_course(reg['course_id'])
    now = datetime.now()
    is_frozen = False
    valid_for_promotion = True

    if now >= course['freeze_time']:
        is_frozen = True
        if now >= course['end_time']:
            valid_for_promotion = False

    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        now = datetime.now()

        new_status = 'frozen' if is_frozen else 'dropped'
        cur.execute("""
            UPDATE registrations
            SET status = %s, dropout_time = %s, updated_at = %s
            WHERE id = %s AND status NOT IN ('checked_in', 'dropped', 'frozen')
            RETURNING *
        """, (new_status, now, now, reg_id))
        updated_reg = cur.fetchone()

        if not updated_reg:
            conn.rollback()
            return None, "退课失败，状态可能已变更"

        was_normal = not reg['is_waitlist']

        if not is_frozen and was_normal and not reg['is_waitlist']:
            pre_deduction = query_one("""
                SELECT cd.*, mp.package_name FROM course_deductions cd
                LEFT JOIN member_packages mp ON cd.package_id = mp.id
                WHERE cd.registration_id = %s AND cd.deduction_type = 'pre_deduct'
                ORDER BY cd.created_at DESC LIMIT 1
            """, (reg_id,))
            if pre_deduction:
                package_module.return_pre_deduct(reg_id, pre_deduction['package_id'], cur, "正常退课返还预占课次")

        if reg['is_waitlist'] and reg['status'] == 'waitlist':
            cur.execute("""
                UPDATE registrations
                SET waitlist_order = waitlist_order - 1, updated_at = %s
                WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
                  AND waitlist_order > %s
            """, (now, reg['course_id'], reg['waitlist_order']))

            cur.execute("""
                INSERT INTO waitlist_history (registration_id, course_id, action, old_waitlist_order, notes)
                VALUES (%s, %s, %s, %s, %s)
            """, (reg_id, reg['course_id'], 'leave_waitlist', reg['waitlist_order'], '退出候补队列'))

        cur.execute("""
            SELECT COUNT(*) as cnt FROM registrations
            WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
        """, (reg['course_id'],))
        current_waitlist = cur.fetchone()['cnt']
        cur.execute("UPDATE courses SET waitlist_count = %s WHERE id = %s",
                    (current_waitlist, reg['course_id']))

        promoted_info = None
        if was_normal and valid_for_promotion:
            promoted_info = _promote_next_waitlist_internal(cur, reg['course_id'], now, reg['id'])

        conn.commit()

        result_reg = dict(updated_reg)
        msg = "冻结成功（已进入冻结期）" if is_frozen else "退课成功"
        if promoted_info:
            msg += f"，候补会员{promoted_info['member_name']}已自动转正"
            result_reg['promoted'] = promoted_info
        return result_reg, msg


def _promote_next_waitlist_internal(cur, course_id, now, dropout_reg_id=None):
    cur.execute("""
        SELECT * FROM registrations
        WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
        ORDER BY waitlist_order ASC
        LIMIT 1
        FOR UPDATE
    """, (course_id,))
    first_waitlist = cur.fetchone()

    if not first_waitlist:
        return None

    cur.execute("""
        UPDATE registrations
        SET is_waitlist = FALSE, waitlist_order = NULL, status = 'registered',
            promoted_from_waitlist = TRUE, updated_at = %s
        WHERE id = %s
        RETURNING *
    """, (now, first_waitlist['id']))
    promoted = cur.fetchone()

    cur.execute("""
        UPDATE registrations
        SET waitlist_order = waitlist_order - 1, updated_at = %s
        WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
          AND waitlist_order > %s
    """, (now, course_id, first_waitlist['waitlist_order']))

    cur.execute("""
        INSERT INTO waitlist_history (registration_id, course_id, action, old_waitlist_order, notes)
        VALUES (%s, %s, %s, %s, %s)
    """, (first_waitlist['id'], course_id, 'promoted', first_waitlist['waitlist_order'],
          f"候补转正，因退课: {dropout_reg_id or '系统调整'}"))

    cur.execute("""
        SELECT COUNT(*) as cnt FROM registrations
        WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
    """, (course_id,))
    new_waitlist_count = cur.fetchone()['cnt']
    cur.execute("UPDATE courses SET waitlist_count = %s WHERE id = %s",
                (new_waitlist_count, course_id))

    return dict(promoted)


def promote_waitlist(reg_id):
    reg = get_registration(reg_id)
    if not reg:
        return None, "报名记录不存在"
    if not reg['is_waitlist'] or reg['status'] != 'waitlist':
        return None, "该会员不在候补队列中"

    course = course_module.get_course(reg['course_id'])
    normal_count = course_module.get_normal_registration_count(reg['course_id'])

    if normal_count >= course['max_students']:
        return None, "正式名额已满，无法手动转正"

    with get_db_connection() as conn:
        cur = get_db_cursor(conn)
        now = datetime.now()

        cur.execute("""
            UPDATE registrations
            SET is_waitlist = FALSE, waitlist_order = NULL, status = 'registered',
                promoted_from_waitlist = TRUE, updated_at = %s
            WHERE id = %s
            RETURNING *
        """, (now, reg_id))
        promoted = cur.fetchone()

        cur.execute("""
            UPDATE registrations
            SET waitlist_order = waitlist_order - 1, updated_at = %s
            WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
              AND waitlist_order > %s
        """, (now, reg['course_id'], reg['waitlist_order']))

        cur.execute("""
            INSERT INTO waitlist_history (registration_id, course_id, action, old_waitlist_order, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (reg_id, reg['course_id'], 'manual_promoted', reg['waitlist_order'], '手动转正'))

        cur.execute("""
            SELECT COUNT(*) as cnt FROM registrations
            WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
        """, (reg['course_id'],))
        new_count = cur.fetchone()['cnt']
        cur.execute("UPDATE courses SET waitlist_count = %s WHERE id = %s",
                    (new_count, reg['course_id']))

        pkg = package_module.select_available_package(reg['member_phone'], course['store_id'], cur)
        pkg_name = None
        if pkg:
            deduction, ded_err = package_module.pre_deduct(reg_id, pkg['id'], cur)
            if ded_err:
                conn.rollback()
                return None, f"转正成功但套餐预占失败：{ded_err}"
            pkg_name = pkg.get('package_name', '')

        conn.commit()
        msg = "候补转正成功"
        if pkg_name:
            msg += f"（已从套餐「{pkg_name}」预占1次）"
        else:
            msg += "（该会员暂无可用套餐）"
        return dict(promoted), msg


def mark_no_show(reg_id):
    reg = get_registration(reg_id)
    if not reg:
        return None, "报名记录不存在"
    if reg['status'] == 'checked_in':
        return None, "该会员已签到，不能标记失约"
    if reg['status'] == 'dropped' or reg['status'] == 'frozen':
        return None, "该会员已退课/冻结"

    course = course_module.get_course(reg['course_id'])
    now = datetime.now()
    if now < course['end_time']:
        return None, "课程尚未结束，暂不能标记失约"

    result = execute("""
        UPDATE registrations SET status = %s, updated_at = %s
        WHERE id = %s AND status IN ('registered')
    """, ('no_show', now, reg_id))
    if result > 0:
        blacklist_module.check_and_auto_blacklist(reg['member_phone'], reg['member_name'])
        pre_deduction = query_one("""
            SELECT cd.*, mp.package_name, mp.remaining_count, mp.reserved_count FROM course_deductions cd
            LEFT JOIN member_packages mp ON cd.package_id = mp.id
            WHERE cd.registration_id = %s AND cd.deduction_type = 'pre_deduct'
            ORDER BY cd.created_at DESC LIMIT 1
        """, (reg_id,))
        pkg_info = ""
        if pre_deduction:
            with get_db_connection() as conn:
                cur = get_db_cursor(conn)
                _, ded_err = package_module.formal_deduct(reg_id, pre_deduction['package_id'], cur)
                if not ded_err:
                    pkg_info = f"（套餐「{pre_deduction['package_name'] or ''}」已扣课，失约不返还）"
                conn.commit()
        return get_registration(reg_id), f"已标记为失约{pkg_info}"
    return None, "标记失败"


def process_no_shows_for_course(course_id):
    course = course_module.get_course(course_id)
    if not course:
        return 0
    now = datetime.now()
    if now < course['end_time']:
        return 0
    affected_phones = query_all("""
        SELECT DISTINCT member_phone, member_name FROM registrations
        WHERE course_id = %s AND status = 'registered' AND is_waitlist = FALSE
          AND checkin_time IS NULL
    """, (course_id,))
    result = execute("""
        UPDATE registrations SET status = 'no_show', updated_at = %s
        WHERE course_id = %s AND status = 'registered' AND is_waitlist = FALSE
          AND checkin_time IS NULL
    """, (now, course_id))
    if result > 0:
        for row in affected_phones:
            blacklist_module.check_and_auto_blacklist(row['member_phone'], row['member_name'])
        no_show_regs = query_all("""
            SELECT id FROM registrations
            WHERE course_id = %s AND status = 'no_show' AND is_waitlist = FALSE
              AND checkin_time IS NULL
        """, (course_id,))
        for nsr in no_show_regs:
            pre_deduction = query_one("""
                SELECT cd.package_id FROM course_deductions cd
                WHERE cd.registration_id = %s AND cd.deduction_type = 'pre_deduct'
                ORDER BY cd.created_at DESC LIMIT 1
            """, (nsr['id'],))
            if pre_deduction:
                with get_db_connection() as conn:
                    cur = get_db_cursor(conn)
                    package_module.formal_deduct(nsr['id'], pre_deduction['package_id'], cur)
                    conn.commit()
    return result
