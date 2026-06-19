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
            create_default_admin()

    print()
    print("=" * 50)
    print("初始化完成！请运行: python app.py")
    print("默认账号: admin / admin")
    print("=" * 50)
