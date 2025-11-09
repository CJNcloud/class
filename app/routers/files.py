import os
import uuid
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/files", tags=["files"])

# 配置上传目录
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 允许的文件类型（可以根据需要扩展）
ALLOWED_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"},
    "document": {".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx"},
    "video": {".mp4", ".avi", ".mov", ".wmv"},
    "audio": {".mp3", ".wav", ".ogg", ".m4a"},
}

# 最大文件大小（10MB）
MAX_FILE_SIZE = 10 * 1024 * 1024


class FileUploadResponse(BaseModel):
    url: str = Field(..., description="文件访问URL")
    filename: str = Field(..., description="保存的文件名")
    size: int = Field(..., description="文件大小（字节）")
    content_type: str = Field(..., description="文件MIME类型")
    uploaded_at: datetime = Field(..., description="上传时间")


def get_file_category(content_type: str, filename: str) -> str:
    """根据文件类型和扩展名判断文件类别"""
    ext = Path(filename).suffix.lower()
    
    if ext in ALLOWED_EXTENSIONS["image"] or content_type.startswith("image/"):
        return "images"
    elif ext in ALLOWED_EXTENSIONS["document"] or content_type.startswith("application/"):
        return "documents"
    elif ext in ALLOWED_EXTENSIONS["video"] or content_type.startswith("video/"):
        return "videos"
    elif ext in ALLOWED_EXTENSIONS["audio"] or content_type.startswith("audio/"):
        return "audios"
    else:
        return "others"


@router.post("/upload", response_model=FileUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...)):
    """
    上传文件接口
    
    - 支持多种文件类型（图片、文档、视频、音频等）
    - 文件大小限制：10MB
    - 返回文件的访问URL
    """
    try:
        # 读取文件内容
        contents = await file.read()
        file_size = len(contents)
        
        # 检查文件大小
        if file_size > MAX_FILE_SIZE:
            logger.warning(f"文件上传失败: 文件过大 size={file_size}, max={MAX_FILE_SIZE}")
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件大小超过限制（最大 {MAX_FILE_SIZE // 1024 // 1024}MB）"
            )
        
        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件为空"
            )
        
        # 获取文件扩展名
        original_filename = file.filename or "file"
        ext = Path(original_filename).suffix.lower()
        
        # 生成唯一文件名
        file_category = get_file_category(file.content_type or "", original_filename)
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        
        # 按类别创建子目录
        category_dir = UPLOAD_DIR / file_category
        category_dir.mkdir(exist_ok=True)
        
        # 保存文件
        file_path = category_dir / unique_filename
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # 生成访问URL（相对路径，前端需要根据实际部署情况拼接完整URL）
        file_url = f"/api/files/{file_category}/{unique_filename}"
        
        logger.info(
            f"文件上传成功: filename={original_filename}, "
            f"saved_as={unique_filename}, size={file_size}, "
            f"category={file_category}, url={file_url}"
        )
        
        return FileUploadResponse(
            url=file_url,
            filename=unique_filename,
            size=file_size,
            content_type=file.content_type or "application/octet-stream",
            uploaded_at=datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"文件上传失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件上传失败: {str(e)}"
        )


@router.get("/{category}/{filename}")
async def get_file(category: str, filename: str):
    """
    获取上传的文件
    
    - category: 文件类别（images, documents, videos, audios, others）
    - filename: 文件名
    """
    # 安全检查：防止路径遍历攻击
    if ".." in category or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径")
    
    file_path = UPLOAD_DIR / category / filename
    
    if not file_path.exists():
        logger.warning(f"文件不存在: category={category}, filename={filename}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    
    # 确保文件在允许的目录内
    try:
        file_path.resolve().relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径")
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/octet-stream",
    )


@router.delete("/{category}/{filename}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(category: str, filename: str):
    """
    删除上传的文件
    
    - category: 文件类别（images, documents, videos, audios, others）
    - filename: 文件名
    """
    # 安全检查
    if ".." in category or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径")
    
    file_path = UPLOAD_DIR / category / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")
    
    # 确保文件在允许的目录内
    try:
        file_path.resolve().relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的文件路径")
    
    try:
        file_path.unlink()
        logger.info(f"文件删除成功: category={category}, filename={filename}")
        return None
    except Exception as e:
        logger.error(f"文件删除失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"文件删除失败: {str(e)}"
        )

