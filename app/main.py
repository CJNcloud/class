from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import users as users_router
from .routers import groups as groups_router
from .routers import group_members as group_members_router
from .routers import chats as chats_router
from .routers import reports as reports_router
from .routers import files as files_router


def create_app() -> FastAPI:
    # Ensure all tables are created on startup
    Base.metadata.create_all(bind=engine)

    app = FastAPI(title="Class Chat Management API", version="0.1.0")

    # 配置CORS：允许所有来源
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 允许的前端来源
        allow_methods=["*"],  # 允许所有HTTP方法（GET, POST, PUT, DELETE等）
        allow_headers=["*"],  # 允许所有请求头（包括X-User-Id, X-Admin-Token等）
        expose_headers=["*"],  # 暴露所有响应头
    )

    # 先注册更具体的路由（groups），再注册通用的路由（users）
    # 这样可以避免路由匹配冲突
    app.include_router(groups_router.router, prefix="/api")
    app.include_router(group_members_router.router, prefix="/api")
    app.include_router(chats_router.router, prefix="/api")
    app.include_router(reports_router.router, prefix="/api")
    app.include_router(files_router.router, prefix="/api")
    app.include_router(users_router.router, prefix="/api")

    @app.get("/health")
    def health_check():
        return {"status": "ok"}

    return app


app = create_app()

