# 管理端重构实施日志（2026-02-25）

## 背景问题

- 管理员前端没有直观的用户审核入口。
- 仪表盘统计在前端自行计算，口径不透明。
- 管理员与博主共用一套页面，角色职责混杂，维护成本高。

## 实施目标

1. 管理端与博主端前端彻底分离。
2. 仪表盘统计统一后端计算，并返回口径说明。
3. 管理员审核链路前端可达：用户审核、作业审核、手工指标审核。
4. 保持现有接口兼容，同时增强筛选能力，避免后续返工。

## 设计决策

- 新增管理员独立控制台页面：`/admin/dashboard`。
- 博主仪表盘改为仅博主可见：`/dashboard`。
- 登录后按角色跳转：
  - `admin -> /admin/dashboard`
  - `blogger -> /dashboard`
- 仪表盘统计由 API 返回，不再在前端自行拼口径。

## 已落地改动

### 后端

- 新增 `GET /api/v1/dashboard/blogger`（博主仪表盘数据）。
- 新增 `GET /api/v1/admin/dashboard`（管理员仪表盘数据 + 统计口径）。
- `GET /api/v1/admin/users` 增加筛选：
  - `role`
  - `review_status`
- `GET /api/v1/admin/assignments` 增加筛选：
  - `status`
- 手工补录响应补齐 `assignment_id` 字段，方便管理员审核页面关联。
- 新增前端页面路由：
  - `GET /admin/dashboard`
  - `GET /admin` 自动跳转 `302 -> /admin/dashboard`

### 前端

- 新增管理员独立页面：`frontend/admin_dashboard.html`
  - 用户审核队列（pending / under_review）
  - 作业审核队列（submitted / in_review）
  - 手工指标审核队列（pending）
  - 任务创建 + 候选达人查看 + 自动/指定分配
  - 统计口径展示（来源于后端）
- 重写博主仪表盘：`frontend/dashboard.html`
  - 只展示博主数据
  - 调用 `/api/v1/dashboard/blogger`
- 登录页角色跳转修正：`frontend/login.html`
- 角色守卫增强：`frontend/static/js/client.js`
  - `homeRouteByRole`
  - `redirectByRole`
  - `requireUserWithRoles`
- 博主页面禁止管理员访问并自动分流：
  - `frontend/tasks.html`
  - `frontend/assignments.html`
  - `frontend/profile.html`
- 管理端页面工程化：
  - 内联样式拆分到 `frontend/static/css/admin-dashboard.css`
  - 内联脚本拆分到 `frontend/static/js/admin-dashboard.js`
  - 管理端拆分为独立工作台页面（非锚点单页）：
    - `/admin/dashboard` 总览
    - `/admin/users` 用户审核中心（含详情侧栏）
    - `/admin/reviews` 作业/手工指标审核中心
    - `/admin/tasks` 任务运营中心

### 自动化回归

- 新增管理员控制台回归脚本：`test/admin_console_regression.sh`
- 新增测试造数与清理脚本：`test/admin_console_seed.py`
- 覆盖链路：
  - 用户审核（pending -> under_review -> approved）
  - 任务分配（候选达人查询 + 自动分配）
  - 作业审核（submitted -> in_review -> completed）
  - 手工指标审核（pending -> approved）
- 回归稳定性处理：
  - `waitForFunction` 全量替换为显式轮询超时
  - 清理逻辑按关联关系删除，避免 E2E 数据残留
  - 拆页后脚本调整为跨页面流转：`/admin/users -> /admin/tasks -> /admin/reviews`

### 后端补充

- 新增 `GET /api/v1/admin/users/{user_id}/detail`：
  - 用户基础资料（含三平台账号）
  - 收款信息
  - 分配统计（状态分布、累计收益、最近分配时间）
  - 最近分配列表
  - 最近行为日志
- 新增 `GET /api/v1/admin/users/review-summary`：
  - 返回用户审核总量与四态分布（pending / under_review / approved / rejected）
  - 用于前端审核队列统计卡片，避免前端自行推断口径
- 管理员审核审计补充：
  - `PATCH /api/v1/admin/users/{id}/review` 写入 `user_activity_logs`（action_type=`admin_user_review`）
  - `PATCH /api/v1/admin/users/{id}/weight` 写入 `user_activity_logs`（action_type=`admin_weight_update`）

### 前端继续优化（用户审核页）

- 页面增强：
  - 新增审核队列统计卡（支持一键切换筛选状态）
  - 审核列表支持“点击整行打开详情”
  - 详情页新增实名信息、角色状态、审核时间、资料完整度进度条
  - 详情页新增缺失项提示（联系方式/实名/收款等）
  - 行为日志展示 action_type 标签，便于快速识别管理员动作
- 兼容策略：
  - 保留原有 DOM 关键选择器（`#user-status-filter`、`#user-review-body`）不变
  - 回归脚本无需重写主流程

## 仪表盘口径（核心）

- 博主可用任务：`tasks.status = published`
- 博主进行中任务：`assignments.status in (accepted, submitted, in_review)`
- 博主累计收益：当前用户 `assignments.revenue` 累加
- 管理员待审核用户：`role = blogger AND review_status in (pending, under_review)`
- 管理员待审作业：`assignments.status in (submitted, in_review)`
- 管理员待审手工指标：`manual_metric_submissions.review_status = pending`

## 后续建议（不阻塞本次上线）

1. 为 `/api/v1/dashboard/blogger` 与 `/api/v1/admin/dashboard` 增加 API 回归测试。
2. 接入真实平台数据源后，在口径说明中补充“采集时间窗”定义。
