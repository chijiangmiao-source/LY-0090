from config import query_one, query_all, execute, execute_returning
from datetime import datetime


def get_store(store_id):
    return query_one("SELECT * FROM stores WHERE id = %s", (store_id,))


def list_stores():
    return query_all("SELECT * FROM stores ORDER BY id")


def create_store(name, address=None, phone=None):
    if not name:
        return None, "门店名称不能为空"
    store = execute_returning(
        "INSERT INTO stores (name, address, phone) VALUES (%s, %s, %s) RETURNING *",
        (name, address, phone)
    )
    return store, None


def update_store(store_id, name=None, address=None, phone=None):
    fields = ["updated_at = %s"]
    params = [datetime.now()]
    if name is not None:
        fields.append("name = %s")
        params.append(name)
    if address is not None:
        fields.append("address = %s")
        params.append(address)
    if phone is not None:
        fields.append("phone = %s")
        params.append(phone)
    params.append(store_id)
    sql = f"UPDATE stores SET {', '.join(fields)} WHERE id = %s"
    result = execute(sql, tuple(params))
    if result > 0:
        return get_store(store_id), None
    return None, "门店不存在"


def delete_store(store_id):
    classroom_count = query_one(
        "SELECT COUNT(*) as cnt FROM classrooms WHERE store_id = %s", (store_id,)
    )['cnt']
    if classroom_count > 0:
        return False, f"该门店下还有{classroom_count}个教室，无法删除"
    result = execute("DELETE FROM stores WHERE id = %s", (store_id,))
    return result > 0, None if result > 0 else "门店不存在"


def get_classroom(classroom_id):
    return query_one("""
        SELECT c.*, s.name as store_name 
        FROM classrooms c LEFT JOIN stores s ON c.store_id = s.id 
        WHERE c.id = %s
    """, (classroom_id,))


def list_classrooms(store_id=None):
    if store_id:
        return query_all("""
            SELECT c.*, s.name as store_name 
            FROM classrooms c LEFT JOIN stores s ON c.store_id = s.id 
            WHERE c.store_id = %s ORDER BY c.id
        """, (store_id,))
    return query_all("""
        SELECT c.*, s.name as store_name 
        FROM classrooms c LEFT JOIN stores s ON c.store_id = s.id 
        ORDER BY c.id
    """)


def create_classroom(store_id, name, capacity=20, description=None):
    if not store_id:
        return None, "请选择门店"
    if not name:
        return None, "教室名称不能为空"
    if not get_store(store_id):
        return None, "门店不存在"
    classroom = execute_returning(
        "INSERT INTO classrooms (store_id, name, capacity, description) VALUES (%s, %s, %s, %s) RETURNING *",
        (store_id, name, capacity, description)
    )
    return classroom, None


def update_classroom(classroom_id, store_id=None, name=None, capacity=None, description=None):
    fields = ["updated_at = %s"]
    params = [datetime.now()]
    if store_id is not None:
        if not get_store(store_id):
            return None, "门店不存在"
        fields.append("store_id = %s")
        params.append(store_id)
    if name is not None:
        fields.append("name = %s")
        params.append(name)
    if capacity is not None:
        fields.append("capacity = %s")
        params.append(capacity)
    if description is not None:
        fields.append("description = %s")
        params.append(description)
    params.append(classroom_id)
    sql = f"UPDATE classrooms SET {', '.join(fields)} WHERE id = %s"
    result = execute(sql, tuple(params))
    if result > 0:
        return get_classroom(classroom_id), None
    return None, "教室不存在"


def delete_classroom(classroom_id):
    course_count = query_one(
        "SELECT COUNT(*) as cnt FROM courses WHERE classroom_id = %s", (classroom_id,)
    )['cnt']
    if course_count > 0:
        return False, f"该教室下还有{course_count}门课程，无法删除"
    result = execute("DELETE FROM classrooms WHERE id = %s", (classroom_id,))
    return result > 0, None if result > 0 else "教室不存在"
