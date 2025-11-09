"""
数据库迁移脚本
用于在应用启动时检查和添加缺失的列
"""
from sqlalchemy import text, inspect
from sqlalchemy.exc import OperationalError

from .database import engine


def migrate_add_user_role_column():
    """
    检查并添加 users 表的 role 列（如果不存在）
    """
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('users')]
    
    if 'role' not in columns:
        print("检测到 users 表缺少 role 列，正在添加...")
        try:
            with engine.connect() as conn:
                # 首先创建 ENUM 类型（如果不存在）
                conn.execute(text("""
                    CREATE TYPE IF NOT EXISTS user_role AS ENUM ('admin', 'user')
                """))
                conn.commit()
                
                # 添加 role 列
                conn.execute(text("""
                    ALTER TABLE users 
                    ADD COLUMN role user_role NOT NULL DEFAULT 'user'
                """))
                conn.commit()
                print("✓ 成功添加 role 列到 users 表")
        except OperationalError as e:
            # MySQL 不支持 CREATE TYPE，需要直接使用 ENUM
            if "CREATE TYPE" in str(e) or "syntax error" in str(e).lower():
                try:
                    with engine.connect() as conn:
                        # MySQL 直接使用 ENUM
                        conn.execute(text("""
                            ALTER TABLE users 
                            ADD COLUMN role ENUM('admin', 'user') NOT NULL DEFAULT 'user'
                        """))
                        conn.commit()
                        print("✓ 成功添加 role 列到 users 表（MySQL）")
                except OperationalError as e2:
                    print(f"✗ 添加 role 列失败: {e2}")
                    raise
            else:
                print(f"✗ 添加 role 列失败: {e}")
                raise
    else:
        print("✓ users 表已包含 role 列")


def migrate_add_group_update_request_member_limit():
    """
    检查并添加 group_update_requests 表的 member_limit 列（如果不存在）
    """
    inspector = inspect(engine)
    try:
        columns = [col['name'] for col in inspector.get_columns('group_update_requests')]
        
        if 'member_limit' not in columns:
            print("检测到 group_update_requests 表缺少 member_limit 列，正在添加...")
            try:
                with engine.connect() as conn:
                    # MySQL 直接使用 ALTER TABLE
                    conn.execute(text("""
                        ALTER TABLE group_update_requests 
                        ADD COLUMN member_limit INT NULL
                    """))
                    conn.commit()
                    print("✓ 成功添加 member_limit 列到 group_update_requests 表")
            except OperationalError as e:
                print(f"✗ 添加 member_limit 列失败: {e}")
                # 不抛出异常，允许应用继续启动
        else:
            print("✓ group_update_requests 表已包含 member_limit 列")
    except Exception as e:
        print(f"检查 group_update_requests 表时出现错误: {e}")
        # 表可能不存在，会在应用启动时自动创建


def run_migrations():
    """
    运行所有迁移
    """
    try:
        migrate_add_user_role_column()
        migrate_add_group_update_request_member_limit()
    except Exception as e:
        print(f"迁移过程中出现错误: {e}")
        # 不抛出异常，允许应用继续启动
        # 用户可以在数据库中手动执行 SQL

