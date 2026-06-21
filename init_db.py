import os
from dotenv import load_dotenv
import psycopg2
from psycopg2 import sql

load_dotenv()

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')
DB_NAME = os.getenv('DB_NAME', 'gym_class')


def create_database():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database='postgres'
        )
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute("SELECT 1 FROM pg_catalog.pg_database WHERE datname = %s", (DB_NAME,))
        exists = cur.fetchone()
        if not exists:
            print(f"创建数据库 {DB_NAME}...")
            cur.execute(sql.SQL("CREATE DATABASE {} ENCODING 'UTF8'").format(sql.Identifier(DB_NAME)))
            print(f"数据库 {DB_NAME} 创建成功")
        else:
            print(f"数据库 {DB_NAME} 已存在")

        cur.close()
        conn.close()
    except Exception as e:
        print(f"创建数据库失败: {e}")
        return False
    return True


def create_tables():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cur = conn.cursor()

        schema_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            sql_content = f.read()

        cur.execute(sql_content)
        conn.commit()

        cur.close()
        conn.close()
        print("数据库表结构创建成功")
        return True
    except Exception as e:
        print(f"创建表结构失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_migrations():
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        cur = conn.cursor()

        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'makeup_vouchers'
        """)
        if cur.fetchone()[0] == 0:
            print("执行迁移：创建 makeup_vouchers 表...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS makeup_vouchers (
                    id SERIAL PRIMARY KEY,
                    voucher_code VARCHAR(50) UNIQUE NOT NULL,
                    source_course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    source_registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
                    member_name VARCHAR(100) NOT NULL,
                    member_phone VARCHAR(20) NOT NULL,
                    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    expiry_time TIMESTAMP NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'unused',
                    store_id INTEGER REFERENCES stores(id) ON DELETE SET NULL,
                    used_registration_id INTEGER REFERENCES registrations(id),
                    used_at TIMESTAMP,
                    voided_at TIMESTAMP,
                    void_reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_makeup_vouchers_member_phone ON makeup_vouchers(member_phone);
                CREATE INDEX IF NOT EXISTS idx_makeup_vouchers_status ON makeup_vouchers(status);
                CREATE INDEX IF NOT EXISTS idx_makeup_vouchers_expiry_time ON makeup_vouchers(expiry_time);
                CREATE INDEX IF NOT EXISTS idx_makeup_vouchers_store_id ON makeup_vouchers(store_id);
            """)

        cur.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name = 'leave_requests'
        """)
        if cur.fetchone()[0] == 0:
            print("执行迁移：创建 leave_requests 表...")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS leave_requests (
                    id SERIAL PRIMARY KEY,
                    registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
                    course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                    member_phone VARCHAR(20) NOT NULL,
                    member_name VARCHAR(100),
                    reason TEXT,
                    leave_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(20) NOT NULL DEFAULT 'approved',
                    voucher_id INTEGER REFERENCES makeup_vouchers(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_leave_requests_member_phone ON leave_requests(member_phone);
                CREATE INDEX IF NOT EXISTS idx_leave_requests_course_id ON leave_requests(course_id);
            """)

        cur.execute("""
            SELECT COUNT(*) FROM information_schema.columns
            WHERE table_name = 'course_deductions' AND column_name = 'voucher_id'
        """)
        if cur.fetchone()[0] == 0:
            print("执行迁移：为 course_deductions 添加 voucher_id 列...")
            cur.execute("""
                ALTER TABLE course_deductions ALTER COLUMN package_id DROP NOT NULL;
                ALTER TABLE course_deductions ADD COLUMN voucher_id INTEGER REFERENCES makeup_vouchers(id) ON DELETE SET NULL;
                CREATE INDEX IF NOT EXISTS idx_course_deductions_voucher_id ON course_deductions(voucher_id);
            """)

        cur.execute("""
            INSERT INTO system_config (key, value, description) VALUES
                ('voucher_validity_days', '30', '补课券默认有效天数')
            ON CONFLICT DO NOTHING
        """)

        conn.commit()
        cur.close()
        conn.close()
        print("数据库迁移完成")
        return True
    except Exception as e:
        print(f"数据库迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_default_admin():
    from config import get_db_connection
    from utils import hash_password

    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM users WHERE username = 'admin'")
            exists = cur.fetchone()
            if exists:
                print("默认管理员已存在")
                return True

            pwd_hash = hash_password('admin')
            cur.execute("""
                INSERT INTO users (username, password_hash, real_name, role)
                VALUES (%s, %s, %s, %s)
            """, ('admin', pwd_hash, '系统管理员', 'admin'))
            print("默认管理员创建成功: admin / admin")
        return True
    except Exception as e:
        print(f"创建默认管理员失败: {e}")
        return False


if __name__ == '__main__':
    print("=" * 50)
    print("健身房团课管理系统 - 数据库初始化")
    print("=" * 50)
    print()

    if create_database():
        print()
        if create_tables():
            print()
            run_migrations()
            print()
            create_default_admin()

    print()
    print("=" * 50)
    print("初始化完成！请运行: python app.py")
    print("默认账号: admin / admin")
    print("=" * 50)
