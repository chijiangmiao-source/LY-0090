from config import (
    query_one, query_all, execute, execute_returning, generate_code,
    FREEZE_MINUTES_BEFORE_START, CLASS_DURATION_MINUTES, get_db_connection, get_db_cursor
)
from utils import calculate_freeze_time, calculate_end_time, is_time_conflict
from datetime import datetime
import stores as store_module


def get_course(course_id):
    return query_one("""
        SELECT c.*, s.name as store_name, cl.name as classroom_name, cl.capacity as classroom_capacity
        FROM courses c 
        LEFT JOIN stores s ON c.store_id = s.id 
        LEFT JOIN classrooms cl ON c.classroom_id = cl.id 
        WHERE c.id = %s
    """, (course_id,))


def get_course_by_code(course_code):
    return query_one("""
        SELECT c.*, s.name as store_name, cl.name as classroom_name
        FROM courses c 
        LEFT JOIN stores s ON c.store_id = s.id 
        LEFT JOIN classrooms cl ON c.classroom_id = cl.id 
        WHERE c.course_code = %s
    """, (course_code,))


def list_courses(store_id=None, status=None, date_from=None, date_to=None, keyword=None):
    sql = """
        SELECT c.*, s.name as store_name, cl.name as classroom_name,
            (SELECT COUNT(*) FROM registrations r WHERE r.course_id = c.id AND r.is_waitlist = FALSE AND r.status NOT IN ('dropped', 'frozen')) as registered_count,
            (SELECT COUNT(*) FROM registrations r WHERE r.course_id = c.id AND r.is_waitlist = TRUE AND r.status = 'waitlist') as current_waitlist
        FROM courses c 
        LEFT JOIN stores s ON c.store_id = s.id 
        LEFT JOIN classrooms cl ON c.classroom_id = cl.id 
        WHERE 1=1
    """
    params = []
    if store_id:
        sql += " AND c.store_id = %s"
        params.append(store_id)
    if status:
        sql += " AND c.status = %s"
        params.append(status)
    if date_from:
        sql += " AND c.start_time >= %s"
        params.append(date_from)
    if date_to:
        sql += " AND c.start_time <= %s"
        params.append(date_to)
    if keyword:
        sql += " AND (c.course_name LIKE %s OR c.course_code LIKE %s)"
        params.extend([f"%{keyword}%", f"%{keyword}%"])
    sql += " ORDER BY c.start_time DESC"
    return query_all(sql, tuple(params))


def create_course(course_name, store_id, classroom_id, start_time,
                  max_students=None, instructor=None, end_time=None):
    if not course_name:
        return None, "课程名称不能为空"
    if not store_id:
        return None, "请选择门店"
    if not classroom_id:
        return None, "请选择教室"
    if not start_time:
        return None, "请选择开课时间"
    if isinstance(start_time, str):
        try:
            start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00').replace(' ', 'T'))
        except Exception:
            try:
                start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
            except Exception:
                return None, "时间格式错误"

    store = store_module.get_store(store_id)
    if not store:
        return None, "门店不存在"

    classroom = store_module.get_classroom(classroom_id)
    if not classroom:
        return None, "教室不存在"
    if classroom['store_id'] != store_id:
        return None, "教室不属于所选门店"

    if end_time:
        if isinstance(end_time, str):
            try:
                end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00').replace(' ', 'T'))
            except Exception:
                try:
                    end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M')
                except Exception:
                    return None, "结束时间格式错误"
    else:
        end_time = calculate_end_time(start_time, CLASS_DURATION_MINUTES)

    if max_students is None:
        max_students = classroom['capacity']

    if max_students <= 0:
        return None, "可报名人数必须大于0"

    freeze_time = calculate_freeze_time(start_time, FREEZE_MINUTES_BEFORE_START)

    conflicts = query_all("""
        SELECT id, course_name, start_time, end_time FROM courses
        WHERE classroom_id = %s AND status != 'cancelled'
          AND start_time < %s AND end_time > %s
    """, (classroom_id, end_time, start_time))
    if conflicts:
        return None, f"教室在该时段已被占用：{conflicts[0]['course_name']}"

    course_code = generate_code('COURSE')
    course = execute_returning("""
        INSERT INTO courses (course_code, course_name, store_id, classroom_id,
                           start_time, end_time, max_students, status, freeze_time, instructor)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
    """, (course_code, course_name, store_id, classroom_id,
          start_time, end_time, max_students, 'scheduled', freeze_time, instructor))
    return course, None


def update_course(course_id, course_name=None, store_id=None, classroom_id=None,
                  start_time=None, end_time=None, max_students=None, status=None, instructor=None):
    course = get_course(course_id)
    if not course:
        return None, "课程不存在"

    if course['status'] != 'scheduled' and status is None:
        return None, "课程已开始或已结束，无法修改"

    fields = ["updated_at = %s"]
    params = [datetime.now()]

    if store_id is not None:
        if not store_module.get_store(store_id):
            return None, "门店不存在"
        fields.append("store_id = %s")
        params.append(store_id)

    if classroom_id is not None:
        classroom = store_module.get_classroom(classroom_id)
        if not classroom:
            return None, "教室不存在"
        target_store_id = store_id or course['store_id']
        if classroom['store_id'] != target_store_id:
            return None, "教室不属于所选门店"
        fields.append("classroom_id = %s")
        params.append(classroom_id)

    new_start = course['start_time']
    new_end = course['end_time']
    new_classroom = classroom_id or course['classroom_id']

    if start_time is not None:
        if isinstance(start_time, str):
            try:
                start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00').replace(' ', 'T'))
            except Exception:
                try:
                    start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
                except Exception:
                    return None, "时间格式错误"
        new_start = start_time
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
                    return None, "结束时间格式错误"
        new_end = end_time
        fields.append("end_time = %s")
        params.append(end_time)

    if (start_time is not None or classroom_id is not None) and new_start and new_end:
        conflicts = query_all("""
            SELECT id, course_name FROM courses
            WHERE classroom_id = %s AND id != %s AND status != 'cancelled'
              AND start_time < %s AND end_time > %s
        """, (new_classroom, course_id, new_end, new_start))
        if conflicts:
            return None, f"教室在该时段已被占用：{conflicts[0]['course_name']}"

    if start_time is not None:
        freeze_time = calculate_freeze_time(new_start, FREEZE_MINUTES_BEFORE_START)
        fields.append("freeze_time = %s")
        params.append(freeze_time)

    if course_name is not None:
        fields.append("course_name = %s")
        params.append(course_name)
    if max_students is not None:
        if max_students <= 0:
            return None, "可报名人数必须大于0"
        fields.append("max_students = %s")
        params.append(max_students)
    if status is not None:
        fields.append("status = %s")
        params.append(status)
    if instructor is not None:
        fields.append("instructor = %s")
        params.append(instructor)

    params.append(course_id)
    sql = f"UPDATE courses SET {', '.join(fields)} WHERE id = %s"
    result = execute(sql, tuple(params))
    if result > 0:
        return get_course(course_id), None
    return None, "更新失败"


def delete_course(course_id):
    course = get_course(course_id)
    if not course:
        return False, "课程不存在"
    reg_count = query_one(
        "SELECT COUNT(*) as cnt FROM registrations WHERE course_id = %s AND status NOT IN ('dropped')",
        (course_id,)
    )['cnt']
    if reg_count > 0:
        return False, f"该课程下还有{reg_count}条报名记录，无法删除，请先取消课程"
    result = execute("DELETE FROM courses WHERE id = %s", (course_id,))
    return result > 0, None if result > 0 else "课程不存在"


def update_course_status_auto():
    now = datetime.now()
    execute("""
        UPDATE courses SET status = 'ongoing', updated_at = %s
        WHERE status = 'scheduled' AND start_time <= %s AND end_time > %s
    """, (now, now, now))
    execute("""
        UPDATE courses SET status = 'completed', updated_at = %s
        WHERE status IN ('scheduled', 'ongoing') AND end_time <= %s
    """, (now, now))
    return True


def get_course_registrations(course_id, include_waitlist=True):
    sql = """
        SELECT r.* FROM registrations r
        WHERE r.course_id = %s
    """
    params = [course_id]
    if not include_waitlist:
        sql += " AND r.is_waitlist = FALSE"
    sql += " ORDER BY CASE WHEN r.is_waitlist THEN r.waitlist_order ELSE r.registration_time END"
    return query_all(sql, tuple(params))


def get_course_normal_registrations(course_id):
    return query_all("""
        SELECT r.* FROM registrations r
        WHERE r.course_id = %s AND r.is_waitlist = FALSE
        ORDER BY r.registration_time
    """, (course_id,))


def get_course_waitlist(course_id):
    return query_all("""
        SELECT r.* FROM registrations r
        WHERE r.course_id = %s AND r.is_waitlist = TRUE AND r.status = 'waitlist'
        ORDER BY r.waitlist_order
    """, (course_id,))


def get_normal_registration_count(course_id):
    return query_one("""
        SELECT COUNT(*) as cnt FROM registrations
        WHERE course_id = %s AND is_waitlist = FALSE AND status NOT IN ('dropped', 'frozen')
    """, (course_id,))['cnt']


def get_waitlist_count(course_id):
    return query_one("""
        SELECT COUNT(*) as cnt FROM registrations
        WHERE course_id = %s AND is_waitlist = TRUE AND status = 'waitlist'
    """, (course_id,))['cnt']
