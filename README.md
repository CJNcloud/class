# Class Chat Management API (FastAPI + MySQL)

This project is a backend for a class group chat management system. The initial version implements user management: register, list, get, update, delete, and simple login. Email fields are not used. Supports basic roles: admin and user.

## Requirements
- Python 3.10+
- MySQL 8+

## Setup
1. Create database (if not exists):
   ```sql
   CREATE DATABASE IF NOT EXISTS class CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```
2. (Optional) Create a `.env` file in the project root to override defaults:
   ```env
   MYSQL_USER=root
   MYSQL_PASSWORD=CJN_cloud
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3306
   MYSQL_DB=class
   ```
   By default, the app assumes user `root`, password `CJN_cloud`, database `class` on `127.0.0.1:3306`.

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Run the server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

Open API docs at: http://127.0.0.1:8000/docs

## API Overview

### 权限说明
- `X-User-Id`: 用户ID Header，用于标识当前用户
- `X-Admin-Token: dev-admin`: 管理员权限 Header

### Users
- POST `/api/users/` - Register user (body: `username`, `phone`, `email`, `password`)
- GET `/api/users/` - List users (supports `skip`, `limit`, `q`)
- GET `/api/users/{id}` - Get user by id
- PUT `/api/users/{id}` - Update user (body: `username?`, `phone?`, `email?`, `password?` - all optional)
- DELETE `/api/users/{id}` - Delete user
- POST `/api/users/login` - Login (body: `login_identifier` (username/phone/email), `password`)
- POST `/api/users/reset-password` - Reset password (body: `identifier` (username/phone/email), `new_password`)
- POST `/api/users/{id}/change-password` - Admin change user password (Header: `X-Admin-Token: dev-admin`, body: `new_password`) - 管理员修改任意用户密码
- POST `/api/users/{id}/role?role=admin|user` - Change role (Header: `X-Admin-Token: dev-admin`)

### Groups
- POST `/api/groups/` - 提交建群请求（产生一条建群申请，待审核）
- GET `/api/groups/create-requests` - 查看建群请求列表（默认显示待审核，支持 `audit_state`、`q`、`skip`、`limit` 参数）
- POST `/api/groups/create-requests/{request_id}/audit?action=approve|reject` - 审核建群请求，通过后创建正式群并分配群号
- GET `/api/groups/` - List groups (filters: `audit_state`, `q`)
- GET `/api/groups/my` - 获取用户自己的群聊列表（Header: `X-User-Id`；包含用户级别的置顶状态；一次性返回所有数据；按置顶状态和创建时间排序）
- GET `/api/groups/{group_id}` - Get group
- POST `/api/groups/{group_id}/pin` - 置顶/取消置顶群聊（Header: `X-User-Id`，请求体: `{"is_pinned": true}` 或 `{"is_pinned": false}`，任何群成员可以操作）
- POST `/api/groups/{group_id}/update-requests` - 提交群信息修改请求（Header: `X-User-Id`，仅群主可以操作）
- GET `/api/groups/update-requests` - 查看群信息修改请求列表（Header: `X-Admin-Token: dev-admin`；默认显示待审核，支持 `audit_state`、`group_id`、`skip`、`limit` 参数）
- POST `/api/groups/update-requests/{request_id}/audit?action=approve|reject` - 审核群信息修改请求（Header: `X-Admin-Token: dev-admin`）
- DELETE `/api/groups/{group_id}` - 解散群（Header: `X-User-Id` 或 `X-Admin-Token`；仅群主或管理员可以解散，会删除成员与消息）

### Group Members
- POST `/api/groups/{group_id}/join-requests` - 提交入群申请
- GET `/api/groups/{group_id}/join-requests?state=未审核&skip=0&limit=50` - 入群申请列表（Header: `X-User-Id` 或 `X-Admin-Token`；群主或管理员可以查看）
- POST `/api/groups/join-requests/{request_id}/audit?action=approve|reject` - 审核入群（Header: `X-User-Id` 或 `X-Admin-Token`；群主或管理员可以审核）
- GET `/api/groups/{group_id}/members` - List group members
- POST `/api/groups/{group_id}/members/{user_id}/admin?is_admin=true|false` - Set/unset member as group admin (Header: `X-Admin-Token: dev-admin`)
- DELETE `/api/groups/{group_id}/members/{user_id}` - 移除成员（Header: `X-User-Id` 或 `X-Admin-Token`；群主可以踢出除自己外的成员，管理员可以踢出任何成员，本人可以通过此接口退出；群主不能通过此接口移除自己，需使用转让功能）
- DELETE `/api/groups/{group_id}/members/me?new_owner_user_id=` - 自己退出群（Header: `X-User-Id`）；若本人是群主需指定 `new_owner_user_id`
- POST `/api/groups/{group_id}/transfer?to_user_id=` - 群主转让群主身份给群内成员（Header: `X-User-Id`，仅群主可以操作）
- GET `/api/groups/{group_id}/members/search?q=` - 按昵称模糊搜索成员

### Reports（举报）
- POST `/api/reports/` - 发起举报（body: `user_id`, `report_content`, `reported_user_id?`, `group_id?`, `chat_message_id?`）

**用户接口：**
- GET `/api/reports/my` - 查看我的举报列表（Header: `X-User-Id`；可选参数：`state`, `skip`, `limit`）
- DELETE `/api/reports/{report_id}` - 删除自己的举报（Header: `X-User-Id`）

**管理员接口：**
- GET `/api/reports/` - 查看所有举报（Header: `X-Admin-Token: dev-admin`；可选筛选：`state`, `reported_user_id`, `group_id`, `skip`, `limit`）
- POST `/api/reports/{report_id}/audit?action=approve|reject` - 审核举报（Header: `X-Admin-Token: dev-admin`）

入群申请新增字段：`reason`（申请理由），在提交与列表接口中返回。

  ### Group Chats
  - POST `/api/groups/{group_id}/chats/` - Send message (body: `chat_no?`, `user_id`, `sender_name?`, `content`)；未提供 `chat_no` 时按群内自增生成（需要是群成员）
  - GET `/api/groups/{group_id}/chats/?skip=0&limit=50&min_chat_no=&q=` - 获取群聊消息列表/查找群聊记录（Header: `X-User-Id`，必须是群成员或群主）：
    - 支持关键字搜索：使用参数 `q` 进行模糊匹配消息内容
    - 支持分页：`skip` 和 `limit` 参数
    - 支持按消息序号筛选：`min_chat_no` 参数
  - DELETE `/api/groups/{group_id}/chats/{message_id}` - 撤回消息（Header: `X-User-Id`）：
    - 发送者：2 分钟内可撤回自己的消息
    - 群主：可随时撤回任意消息
    - 撤回后通过 WebSocket 推送撤回事件
  - WebSocket: `ws://<host>/api/groups/{group_id}/chats/ws`
    - 服务器会推送事件：
      - `{"event":"message", "data": {...}}` - 新消息
      - `{"event":"retracted", "data": {"message_id":..}}` - 消息撤回
  - 清空群聊信息：属于客户端本地行为，无需服务端接口（前端删除本地缓存的聊天记录即可）

### Files（文件上传）
- POST `/api/files/upload` - 上传文件（multipart/form-data，字段名：`file`）
  - 支持文件类型：图片（jpg, png, gif等）、文档（pdf, doc等）、视频（mp4, avi等）、音频（mp3, wav等）
  - 文件大小限制：10MB
  - 自动按文件类型分类存储（images, documents, videos, audios, others）
  - 返回响应：`{"url": "/api/files/images/xxx.jpg", "filename": "xxx.jpg", "size": 102400, "content_type": "image/jpeg", "uploaded_at": "..."}`
- GET `/api/files/{category}/{filename}` - 获取上传的文件（category: images/documents/videos/audios/others）
- DELETE `/api/files/{category}/{filename}` - 删除上传的文件

## Notes
- Passwords are hashed with bcrypt via passlib.
- Tables are auto-created on startup.
 - Role management currently uses a simple header gate for demo: send `X-Admin-Token: dev-admin`. Replace with real auth later.
 - 建群字段：`name`, `created_by_user_id`, `member_limit`, `avatar_url`, `announce_limit`, `announce`, `group_type`, `note`；建群后默认 `audit_state=未审核`，管理员审核通过后才允许加入与聊天。
 - WebSocket 示例（浏览器控制台）：
   ```js
   const ws = new WebSocket('ws://127.0.0.1:8000/api/groups/1/chats/ws');
   ws.onmessage = (e) => console.log('WS:', e.data);
   ```
 - 本地删除/清空消息属于客户端行为，不影响服务器端记录（无需服务端接口）。

