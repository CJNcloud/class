# 群聊系统完整使用流程

## 功能完整性检查 ✅

当前项目已实现以下核心功能：

### ✅ 已实现功能列表
1. **用户管理**：注册、登录、角色管理（admin/user）
2. **群聊管理**：建群申请、管理员审核、群信息修改、解散
3. **成员管理**：申请加入、群主审核、退出、转让、搜索
4. **消息功能**：发送消息、查看历史、搜索、撤回
5. **实时通信**：WebSocket 推送新消息和撤回事件
6. **举报功能**：提交举报、查看状态、管理员审核

**结论：核心功能已完整实现，可以完成从建群到实时聊天的完整流程。**

---

## 完整流程：建立群聊 → 实时发送消息

### 步骤 1：注册用户
```bash
POST http://127.0.0.1:8000/api/users/
Content-Type: application/json

{
  "username": "alice",
  "password": "123456"
}
```
响应会返回用户ID（例如：`{"id": 1, "username": "alice", ...}`）

### 步骤 2：创建管理员（可选，用于审核）
```bash
POST http://127.0.0.1:8000/api/users/1/role?role=admin
Header: X-Admin-Token: dev-admin
```

### 步骤 3：提交建群申请
```bash
POST http://127.0.0.1:8000/api/groups/
Content-Type: application/json

{
  "name": "班级一群",
  "created_by_user_id": 1,
  "member_limit": 50,
  "avatar_url": "https://example.com/avatar.jpg",
  "announce_limit": 5,
  "announce": "欢迎加入",
  "group_type": "class",
  "note": "一班群聊"
}
```
响应返回建群申请ID（例如：`{"id": 1, "audit_state": "未审核", ...}`）

### 步骤 4：管理员审核建群申请
```bash
POST http://127.0.0.1:8000/api/groups/create-requests/1/audit?action=approve
Header: X-Admin-Token: dev-admin
```
**审核通过后，系统会创建正式群并分配群号（GroupID）**，响应会返回群信息：
```json
{
  "id": 1,  // 这就是群号 GroupID
  "name": "班级一群",
  "audit_state": "审核通过",
  ...
}
```

### 步骤 5：用户申请加入群
```bash
POST http://127.0.0.1:8000/api/groups/1/join-requests
Content-Type: application/json

{
  "user_id": 2,
  "nickname": "Bob",
  "reason": "想加入班级群"
}
```

### 步骤 6：群主审核入群申请
```bash
POST http://127.0.0.1:8000/api/groups/join-requests/1/audit?action=approve
Header: X-User-Id: 1  # 群主的ID
```
**审核通过后，用户正式加入群聊。**

### 步骤 7：连接 WebSocket 实时接收消息
```javascript
// 浏览器控制台或前端代码
const ws = new WebSocket('ws://127.0.0.1:8000/api/groups/1/chats/ws');

ws.onopen = () => {
  console.log('WebSocket 已连接');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('收到消息:', data);
  
  if (data.event === 'message') {
    // 新消息
    console.log(`${data.data.sender_name}: ${data.data.content}`);
  } else if (data.event === 'retracted') {
    // 消息撤回
    console.log(`消息 ${data.data.message_id} 已撤回`);
  }
};

ws.onerror = (error) => {
  console.error('WebSocket 错误:', error);
};

ws.onclose = () => {
  console.log('WebSocket 已断开');
};
```

### 步骤 8：发送消息
```bash
POST http://127.0.0.1:8000/api/groups/1/chats/
Content-Type: application/json

{
  "user_id": 2,
  "sender_name": "Bob",
  "content": "大家好！"
}
```

**发送后：**
- 消息会保存到数据库
- 通过 WebSocket 自动推送给所有连接到该群的客户端
- 所有在线的群成员都能实时收到消息

### 步骤 9：查看历史消息
```bash
GET http://127.0.0.1:8000/api/groups/1/chats/?skip=0&limit=50
```

### 步骤 10：撤回消息（可选）
```bash
DELETE http://127.0.0.1:8000/api/groups/1/chats/123
Header: X-User-Id: 2
```
- 发送者：2分钟内可撤回
- 群主：可随时撤回
- 撤回后通过 WebSocket 推送 `retracted` 事件

---

## 实时消息流程说明

### WebSocket 工作原理
1. **客户端连接**：前端连接到 `ws://127.0.0.1:8000/api/groups/{group_id}/chats/ws`
2. **服务端维护连接池**：每个群都有独立的连接池，存储该群的所有 WebSocket 连接
3. **消息推送**：
   - 用户通过 REST API 发送消息
   - 服务端保存消息到数据库
   - 服务端通过 WebSocket 向该群所有在线客户端推送消息
4. **事件类型**：
   - `{"event": "message", "data": {...}}` - 新消息
   - `{"event": "retracted", "data": {"message_id": ...}}` - 消息撤回

### 前端实现建议
```javascript
class ChatManager {
  constructor(groupId) {
    this.groupId = groupId;
    this.ws = null;
    this.connect();
  }

  connect() {
    this.ws = new WebSocket(`ws://127.0.0.1:8000/api/groups/${this.groupId}/chats/ws`);
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.handleMessage(data);
    };
  }

  handleMessage(data) {
    if (data.event === 'message') {
      // 显示新消息
      this.displayMessage(data.data);
    } else if (data.event === 'retracted') {
      // 移除被撤回的消息
      this.removeMessage(data.data.message_id);
    }
  }

  sendMessage(content, userId, senderName) {
    // 通过 REST API 发送
    fetch(`http://127.0.0.1:8000/api/groups/${this.groupId}/chats/`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        user_id: userId,
        sender_name: senderName,
        content: content
      })
    });
  }
}
```

---

## 快速测试流程

### 使用 curl 测试（命令行）

```bash
# 1. 注册用户1（群主）
curl -X POST "http://127.0.0.1:8000/api/users/" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"123456"}'

# 2. 注册用户2（成员）
curl -X POST "http://127.0.0.1:8000/api/users/" \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","password":"123456"}'

# 3. 设置用户1为管理员（用于审核）
curl -X POST "http://127.0.0.1:8000/api/users/1/role?role=admin" \
  -H "X-Admin-Token: dev-admin"

# 4. 提交建群申请
curl -X POST "http://127.0.0.1:8000/api/groups/" \
  -H "Content-Type: application/json" \
  -d '{"name":"测试群","created_by_user_id":1,"member_limit":50}'

# 5. 管理员审核通过（假设申请ID是1）
curl -X POST "http://127.0.0.1:8000/api/groups/create-requests/1/audit?action=approve" \
  -H "X-Admin-Token: dev-admin"

# 6. 用户2申请加入群（假设群ID是1）
curl -X POST "http://127.0.0.1:8000/api/groups/1/join-requests" \
  -H "Content-Type: application/json" \
  -d '{"user_id":2,"nickname":"Bob","reason":"想加入"}'

# 7. 群主审核通过（假设申请ID是1）
curl -X POST "http://127.0.0.1:8000/api/groups/join-requests/1/audit?action=approve" \
  -H "X-User-Id: 1"

# 8. 用户2发送消息
curl -X POST "http://127.0.0.1:8000/api/groups/1/chats/" \
  -H "Content-Type: application/json" \
  -d '{"user_id":2,"sender_name":"Bob","content":"大家好！"}'

# 9. 查看消息
curl "http://127.0.0.1:8000/api/groups/1/chats/?skip=0&limit=10"
```

### 使用 Postman 或浏览器
1. 打开 `http://127.0.0.1:8000/docs` 查看完整的 API 文档
2. 在 Swagger UI 中直接测试所有接口
3. WebSocket 需要在浏览器控制台或专门的 WebSocket 客户端测试

---

## 总结

✅ **项目功能完整**，已实现：
- 完整的用户管理
- 建群审核流程
- 成员管理（申请、审核、退出、转让）
- 消息发送与接收
- **WebSocket 实时推送**
- 举报功能

✅ **实时聊天流程**：
1. 建群申请 → 管理员审核 → 群创建成功
2. 申请加入 → 群主审核 → 加入成功
3. 连接 WebSocket → 发送消息 → **实时推送给所有在线成员**
4. 查看历史消息、撤回消息等功能都已实现

**现在可以直接使用该系统进行群聊了！** 🎉

