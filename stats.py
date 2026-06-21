from config import query_one, query_all
from datetime import datetime


def get_overall_stats(store_id=None, date_from=None, date_to=None):
    where_clauses = ["c.status != 'cancelled'"]
    params = []
    if store_id:
        where_clauses.append("c.store_id = %s")
        params.append(store_id)
    if date_from:
        where_clauses.append("c.start_time >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("c.start_time <= %s")
        params.append(date_to)
    where_sql = " AND ".join(where_clauses)

    total_courses = query_one(f"""
        SELECT COUNT(*) as cnt FROM courses c WHERE {where_sql}
    """, tuple(params))['cnt']

    completed_courses = query_one(f"""
        SELECT COUNT(*) as cnt FROM courses c WHERE {where_sql} AND c.status = 'completed'
    """, tuple(params))['cnt']

    total_registrations = query_one(f"""
        SELECT COUNT(*) as cnt FROM registrations r
        JOIN courses c ON r.course_id = c.id
        WHERE {where_sql} AND r.is_waitlist = FALSE
    """, tuple(params))['cnt']

    total_capacity = query_one(f"""
        SELECT COALESCE(SUM(c.max_students), 0) as sum FROM courses c
        WHERE {where_sql} AND c.status = 'completed'
    """, tuple(params))['sum']

    actual_attendance = query_one(f"""
        SELECT COUNT(*) as cnt FROM registrations r
        JOIN courses c ON r.course_id = c.id
        WHERE {where_sql} AND c.status = 'completed'
          AND r.is_waitlist = FALSE AND r.status = 'checked_in'
    """, tuple(params))['cnt']

    full_classes = query_one(f"""
        SELECT COUNT(*) as cnt FROM (
            SELECT c.id, c.max_students,
                   COUNT(r.id) FILTER (WHERE r.is_waitlist = FALSE AND r.status NOT IN ('dropped', 'frozen', 'leave')) as reg_cnt
            FROM courses c
            LEFT JOIN registrations r ON r.course_id = c.id
            WHERE {where_sql} AND c.status = 'completed'
            GROUP BY c.id, c.max_students
        ) sub WHERE sub.reg_cnt >= sub.max_students
    """, tuple(params))['cnt']

    waitlist_total = query_one(f"""
        SELECT COUNT(*) as cnt FROM registrations r
        JOIN courses c ON r.course_id = c.id
        WHERE {where_sql} AND r.is_waitlist = TRUE
    """, tuple(params))['cnt']

    waitlist_promoted = query_one(f"""
        SELECT COUNT(*) as cnt FROM registrations r
        JOIN courses c ON r.course_id = c.id
        WHERE {where_sql} AND r.promoted_from_waitlist = TRUE
    """, tuple(params))['cnt']

    no_show_count = query_one(f"""
        SELECT COUNT(*) as cnt FROM registrations r
        JOIN courses c ON r.course_id = c.id
        WHERE {where_sql} AND r.status = 'no_show'
    """, tuple(params))['cnt']

    fill_rate = 0
    if total_capacity > 0:
        fill_rate = round((actual_attendance / total_capacity) * 100, 1)

    full_class_rate = 0
    if completed_courses > 0:
        full_class_rate = round((full_classes / completed_courses) * 100, 1)

    promotion_rate = 0
    if waitlist_total > 0:
        promotion_rate = round((waitlist_promoted / waitlist_total) * 100, 1)

    no_show_rate = 0
    if total_registrations > 0:
        no_show_rate = round((no_show_count / total_registrations) * 100, 1)

    return {
        'total_courses': total_courses,
        'completed_courses': completed_courses,
        'total_registrations': total_registrations,
        'total_capacity': total_capacity,
        'actual_attendance': actual_attendance,
        'full_classes': full_classes,
        'waitlist_total': waitlist_total,
        'waitlist_promoted': waitlist_promoted,
        'no_show_count': no_show_count,
        'fill_rate': fill_rate,
        'full_class_rate': full_class_rate,
        'promotion_rate': promotion_rate,
        'no_show_rate': no_show_rate,
    }


def get_member_no_show_ranking(store_id=None, date_from=None, date_to=None, limit=20):
    where_clauses = ["r.status = 'no_show'"]
    params = []
    if store_id:
        where_clauses.append("c.store_id = %s")
        params.append(store_id)
    if date_from:
        where_clauses.append("c.start_time >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("c.start_time <= %s")
        params.append(date_to)
    where_sql = " AND ".join(where_clauses)

    return query_all(f"""
        SELECT r.member_name, r.member_phone,
               COUNT(*) as no_show_count,
               COUNT(*) FILTER (WHERE r.status = 'checked_in') as checkin_count
        FROM registrations r
        JOIN courses c ON r.course_id = c.id
        WHERE r.member_phone IN (
            SELECT member_phone FROM registrations r2
            JOIN courses c2 ON r2.course_id = c2.id
            WHERE {where_sql}
            GROUP BY r2.member_phone
            HAVING COUNT(*) FILTER (WHERE r2.status = 'no_show') > 0
        )
        GROUP BY r.member_name, r.member_phone
        ORDER BY no_show_count DESC, r.member_name ASC
        LIMIT %s
    """, tuple(params + [limit]))


def get_course_stats_list(store_id=None, date_from=None, date_to=None):
    where_clauses = ["c.status = 'completed'"]
    params = []
    if store_id:
        where_clauses.append("c.store_id = %s")
        params.append(store_id)
    if date_from:
        where_clauses.append("c.start_time >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("c.start_time <= %s")
        params.append(date_to)
    where_sql = " AND ".join(where_clauses)

    return query_all(f"""
        SELECT c.id, c.course_code, c.course_name, c.start_time, c.end_time,
               c.max_students, s.name as store_name, cl.name as classroom_name,
               COUNT(r.id) FILTER (WHERE r.is_waitlist = FALSE AND r.status = 'checked_in') as checked_in,
               COUNT(r.id) FILTER (WHERE r.is_waitlist = FALSE AND r.status = 'no_show') as no_shows,
               COUNT(r.id) FILTER (WHERE r.is_waitlist = FALSE AND r.status = 'dropped') as dropped,
               COUNT(r.id) FILTER (WHERE r.is_waitlist = FALSE AND r.status = 'frozen') as frozen,
               COUNT(r.id) FILTER (WHERE r.is_waitlist = TRUE) as waitlisted,
               COUNT(r.id) FILTER (WHERE r.promoted_from_waitlist = TRUE) as promoted
        FROM courses c
        LEFT JOIN stores s ON c.store_id = s.id
        LEFT JOIN classrooms cl ON c.classroom_id = cl.id
        LEFT JOIN registrations r ON r.course_id = c.id
        WHERE {where_sql}
        GROUP BY c.id, c.course_code, c.course_name, c.start_time, c.end_time,
                 c.max_students, s.name, cl.name
        ORDER BY c.start_time DESC
    """, tuple(params))


def get_store_comparison(date_from=None, date_to=None):
    where_clauses = ["c.status = 'completed'"]
    params = []
    if date_from:
        where_clauses.append("c.start_time >= %s")
        params.append(date_from)
    if date_to:
        where_clauses.append("c.start_time <= %s")
        params.append(date_to)
    where_sql = " AND ".join(where_clauses)

    return query_all(f"""
        SELECT s.id, s.name as store_name,
               COUNT(DISTINCT c.id) as course_count,
               COALESCE(SUM(c.max_students), 0) as total_capacity,
               COUNT(r.id) FILTER (WHERE r.is_waitlist = FALSE AND r.status = 'checked_in') as checked_in,
               COUNT(r.id) FILTER (WHERE r.is_waitlist = FALSE AND r.status = 'no_show') as no_shows,
               COUNT(r.id) FILTER (WHERE r.promoted_from_waitlist = TRUE) as promoted
        FROM stores s
        LEFT JOIN courses c ON c.store_id = s.id AND {where_sql.replace('WHERE ', '')}
        LEFT JOIN registrations r ON r.course_id = c.id
        GROUP BY s.id, s.name
        ORDER BY course_count DESC
    """, tuple(params))
