# Benusy 项目运行与事实基线（给开发者）

## 1. 一键启动

在项目根目录执行：

```bash
./start.sh
```

默认地址：

- 后端 API + 前端页面同源：`http://127.0.0.1:8000`

可覆盖：

```bash
BACKEND_HOST=127.0.0.1 BACKEND_PORT=9000 ./start.sh
```

按 `Ctrl+C` 停止。

## 2. 基础后端约定

- API 前缀：`/api/v1`
- 鉴权：JWT Bearer
- 数据库：SQLite（`database.db`）
- 默认管理员（启动自动确保存在）：
  - 邮箱：`admin@example.com`
  - 密码：`admin123`

## 3. 用户与审核流程

- 角色：`admin | blogger`
- 审核状态：`pending -> under_review -> approved/rejected`
- 规则：
  - 博主注册默认 `pending`
  - 博主仅在 `approved` 后允许登录并接任务
  - 拒绝时必须提供 `review_reason`

## 4. 社媒与任务核心模型

- 社媒账号子表：`douyin_accounts | xiaohongshu_accounts | weibo_accounts`
- 注册时至少一个平台账号
- 任务状态：`draft | published | cancelled`
- 分配状态：`accepted | submitted | in_review | rejected | completed | cancelled`
- 指标同步状态：`normal | manual_required | manual_pending_review | manual_approved | manual_rejected`
- 新增：
  - 收款信息表 `payout_infos`
  - 用户行为日志 `user_activity_logs`

## 5. 收益与指标同步

- 收益公式：
  - `revenue = base_reward + engagement_score * platform_coef * user.weight`
- 平台系数配置：`/api/v1/admin/platform-configs/{platform}`
- 自动同步：成功写入 `metrics(source=auto)`；失败转 `manual_required`
- 手工补录：博主提交后管理员审核，通过后写入 `metrics(source=manual)`

## 6. 新增/关键 API（已落地）

### 博主侧

- 任务：
  - `GET /api/v1/tasks/`
  - `GET /api/v1/tasks/{task_id}`
  - `POST /api/v1/tasks/{task_id}/accept`
- 我的分配：
  - `GET /api/v1/assignments/me`
  - `POST /api/v1/assignments/{assignment_id}/submit`
  - `POST /api/v1/assignments/{assignment_id}/manual-metrics`
- 个人中心：
  - `PATCH /api/v1/users/me/profile`
  - `GET /api/v1/users/me/social-accounts`
  - `POST /api/v1/users/me/accounts/{platform}`
  - `PATCH /api/v1/users/me/accounts/{platform}/{account_id}`
  - `DELETE /api/v1/users/me/accounts/{platform}/{account_id}`
  - `POST /api/v1/users/me/change-password`
  - `GET /api/v1/users/me/payout-info`
  - `PUT /api/v1/users/me/payout-info`
  - `GET /api/v1/users/me/history`

### 管理员侧

- 任务分配逻辑：
  - `GET /api/v1/admin/tasks/{task_id}/eligible-bloggers`
  - `POST /api/v1/admin/tasks/{task_id}/distribute`
- 任务/审核/人工指标：原有 admin 接口保持可用

## 7. 前端当前行为（真实交互）

- 已接入统一客户端：`/static/js/client.js`
  - 自动注入 token
  - `401` 自动清理登录态并跳转 `/login`
  - 登录页支持“记住我”：勾选后 token 长期有效（默认 30 天）且持久化；未勾选为会话级存储
- 页面：
  - `/dashboard`：按角色加载真实统计（admin/blogger）
    - admin 额外支持任务管理面板（新增任务 + 候选达人查看 + 自动分配 + 指定 ID 分配）
  - `/tasks`：真实任务列表、筛选、查看详情、接受任务（admin 为只读）
  - `/assignments`：真实分配列表、状态筛选、提交链接、手工补录、详情（admin 为只读）
  - `/profile`：
    - 个人信息
    - 我的社交与自媒体平台（增删改）
    - 账号安全（改密）
    - 收款信息
    - 历史记录

## 8. 当前限制

- 自动指标抓取仍是模拟集成（`app/services/metrics.py`），真实平台 API 需后续对接
- 仍缺少系统化自动化测试（尤其前端 E2E 与关键后端流程）

## 9. 下一步建议

1. 引入 pytest 覆盖任务分配与个人中心接口
2. 用 Playwright 补登录、接单、提交、补录的回归用例
3. 对接真实平台数据源并替换模拟 `fetch_metrics`
