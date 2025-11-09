"""
创建管理员用户的脚本
运行方式: python create_admin.py
"""
from app.database import SessionLocal, engine
from app.models import Base, User
from app.security import hash_password
from sqlalchemy import select


def create_admin_user():
    """创建管理员用户"""
    # 确保表已创建
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        # 检查管理员是否已存在
        admin_username = "admin"
        existing_admin = db.scalar(select(User).where(User.username == admin_username))
        
        if existing_admin:
            print(f"管理员用户已存在: username={admin_username}, id={existing_admin.id}")
            # 更新为管理员角色（如果之前不是）
            if existing_admin.role != "admin":
                existing_admin.role = "admin"
                db.commit()
                print(f"已将用户 {admin_username} 更新为管理员角色")
            return existing_admin
        
        # 创建新管理员
        admin = User(
            username="admin",
            phone="admin",
            email="admin",
            hashed_password=hash_password("admin"),
            role="admin"
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"管理员用户创建成功!")
        print(f"  - ID: {admin.id}")
        print(f"  - 用户名: {admin.username}")
        print(f"  - 手机号: {admin.phone}")
        print(f"  - 邮箱: {admin.email}")
        print(f"  - 密码: admin")
        print(f"  - 角色: {admin.role}")
        return admin
    except Exception as e:
        db.rollback()
        print(f"创建管理员用户失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_admin_user()

