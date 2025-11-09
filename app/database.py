import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv


load_dotenv()


class Base(DeclarativeBase):
    pass


# Configuration
# Assumptions: MySQL host 127.0.0.1, port 3306, user 'root'
# Password is provided by the user, database name is 'class'
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", os.getenv("DB_PASSWORD", "CJN_cloud"))
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_DB = os.getenv("MYSQL_DB", "class")


DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    f"?charset=utf8mb4&connect_timeout=10"
)


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,  # 连接前检查连接是否有效，自动重连断开的连接
    pool_recycle=3600,  # 1小时后回收连接，避免连接过期
    pool_size=10,  # 连接池大小
    max_overflow=20,  # 最大溢出连接数
    echo=False,  # 设置为True可以打印SQL语句，用于调试
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    """
    数据库会话依赖注入
    自动处理连接关闭和异常回滚
    注意：路由中需要手动调用 db.commit() 来提交事务
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()  # 发生异常时回滚
        raise
    finally:
        db.close()  # 确保连接关闭

