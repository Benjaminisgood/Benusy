(function () {
    let users = [];
    let selectedUserId = null;
    let selectedDetail = null;
    let reviewSummary = null;

    function reviewStatusLabel(status) {
        const map = {
            pending: "待审核",
            under_review: "审核中",
            approved: "已通过",
            rejected: "已驳回",
        };
        return map[status] || status || "-";
    }

    function maskIdNo(raw) {
        const value = (raw || "").trim();
        if (!value) return "-";
        if (value.length <= 8) return value;
        return `${value.slice(0, 4)}********${value.slice(-4)}`;
    }

    function socialAccountCount(user) {
        return (user.douyin_accounts || []).length + (user.xiaohongshu_accounts || []).length + (user.weibo_accounts || []).length;
    }

    function buildCompleteness(user, payout) {
        const checks = [
            { label: "实名信息", ok: Boolean(user.real_name && user.id_no) },
            { label: "联系方式", ok: Boolean(user.phone) },
            { label: "城市与领域", ok: Boolean(user.city && user.category) },
            { label: "至少 1 个社媒账号", ok: socialAccountCount(user) > 0 },
            { label: "收款信息", ok: Boolean(payout && payout.account_no) },
        ];
        const done = checks.filter((item) => item.ok).length;
        const percent = Math.round((done / checks.length) * 100);
        return {
            checks,
            done,
            total: checks.length,
            percent,
            missing: checks.filter((item) => !item.ok).map((item) => item.label),
        };
    }

    function userActions(user) {
        const actions = [`<button class="mini-btn muted" data-action="open-detail" data-user-id="${user.id}">查看详情</button>`];
        if (user.review_status === "pending") {
            actions.push(`<button class="mini-btn primary" data-action="user-review" data-next="under_review" data-user-id="${user.id}">进入审核</button>`);
        } else if (user.review_status === "under_review") {
            actions.push(`<button class="mini-btn success" data-action="user-review" data-next="approved" data-user-id="${user.id}">通过</button>`);
            actions.push(`<button class="mini-btn danger" data-action="user-review" data-next="rejected" data-user-id="${user.id}">驳回</button>`);
        } else if (user.review_status === "rejected") {
            actions.push(`<button class="mini-btn warning" data-action="user-review" data-next="under_review" data-user-id="${user.id}">重新审核</button>`);
        }
        return actions.join("");
    }

    function renderReviewSummary() {
        const container = document.getElementById("review-summary-grid");
        if (!container) return;

        if (!reviewSummary) {
            container.innerHTML = "";
            return;
        }

        const selected = document.getElementById("user-status-filter").value;
        const cards = [
            { key: "pending", label: "待审核", value: reviewSummary.pending || 0 },
            { key: "under_review", label: "审核中", value: reviewSummary.under_review || 0 },
            { key: "approved", label: "已通过", value: reviewSummary.approved || 0 },
            { key: "rejected", label: "已驳回", value: reviewSummary.rejected || 0 },
            { key: "all", label: "全部博主", value: reviewSummary.total || 0 },
        ];

        container.innerHTML = cards.map((item) => {
            const activeClass = selected === item.key ? "active" : "";
            return `
                <button class="summary-card ${activeClass}" data-summary-status="${item.key}" type="button">
                    <p class="label">${escapeHtml(item.label)}</p>
                    <p class="value">${Number(item.value || 0).toLocaleString("zh-CN")}</p>
                </button>
            `;
        }).join("");
    }

    function renderUsers() {
        const body = document.getElementById("user-review-body");
        const keyword = (document.getElementById("user-search-input").value || "").trim().toLowerCase();

        const filtered = users.filter((user) => {
            if (!keyword) return true;
            const text = [
                user.display_name,
                user.username,
                user.email,
                user.city,
                user.category,
                user.real_name,
                (user.tags || []).join(","),
            ].join(" ").toLowerCase();
            return text.includes(keyword);
        });

        if (!filtered.length) {
            body.innerHTML = `<tr><td colspan="6" class="empty">当前筛选条件下无可展示用户</td></tr>`;
            return;
        }

        body.innerHTML = filtered.map((user) => {
            const socialCount = socialAccountCount(user);
            const isSelected = selectedUserId === user.id ? "selected-row" : "";
            return `
                <tr class="${isSelected}" data-row-user-id="${user.id}">
                    <td>${user.id}</td>
                    <td>
                        <strong>${escapeHtml(user.display_name || user.username || "-")}</strong><br>
                        <span class="muted-text">${escapeHtml(user.email || "-")}</span><br>
                        <span class="muted-text">账号数: ${socialCount}</span>
                    </td>
                    <td>${escapeHtml(user.city || "-")} / ${escapeHtml(user.category || "-")}</td>
                    <td>粉丝 ${Number(user.follower_total || 0).toLocaleString("zh-CN")}<br><span class="muted-text">均播 ${Number(user.avg_views || 0).toLocaleString("zh-CN")}</span></td>
                    <td><span class="status ${escapeHtml(user.review_status)}">${escapeHtml(reviewStatusLabel(user.review_status))}</span></td>
                    <td><div class="row-actions">${userActions(user)}</div></td>
                </tr>
            `;
        }).join("");
    }

    function renderAccountGroup(title, platform, accounts) {
        if (!accounts || !accounts.length) {
            return `
                <li class="stack-item">
                    <h5>${title}</h5>
                    <p>未绑定 ${title} 账号</p>
                </li>
            `;
        }

        return accounts.map((item) => `
            <li class="stack-item">
                <h5>${title} · ${escapeHtml(item.account_name || "-")}</h5>
                <p>ID: ${escapeHtml(item.account_id || "-")}</p>
                <p>粉丝: ${Number(item.follower_count || 0).toLocaleString("zh-CN")}</p>
                <p>主页: ${item.profile_url ? `<a href="${escapeHtml(item.profile_url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.profile_url)}</a>` : "-"}</p>
                <p>平台: ${platformLabel(platform)}</p>
            </li>
        `).join("");
    }

    function renderAssignments(detail) {
        const items = detail.recent_assignments || [];
        if (!items.length) {
            return `<div class="empty">暂无历史分配记录</div>`;
        }

        return `
            <div class="table-wrap">
                <table>
                    <thead>
                    <tr>
                        <th>分配ID</th>
                        <th>任务</th>
                        <th>状态</th>
                        <th>收益</th>
                        <th>更新时间</th>
                    </tr>
                    </thead>
                    <tbody>
                    ${items.map((item) => `
                        <tr>
                            <td>${item.assignment_id}</td>
                            <td>${escapeHtml(item.task_title || `任务#${item.task_id}`)}</td>
                            <td><span class="status ${escapeHtml(item.status)}">${escapeHtml(assignmentStatusLabel(item.status))}</span></td>
                            <td>¥${Number(item.revenue || 0).toFixed(2)}</td>
                            <td>${escapeHtml(formatDateTime(item.updated_at))}</td>
                        </tr>
                    `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderActivities(detail) {
        const items = detail.recent_activities || [];
        if (!items.length) {
            return `<div class="empty">暂无行为日志</div>`;
        }

        return `
            <ul class="stack-list">
                ${items.map((item) => `
                    <li class="stack-item">
                        <div class="stack-item-head">
                            <h5>${escapeHtml(item.title || item.action_type || "-")}</h5>
                            <span class="activity-tag">${escapeHtml(item.action_type || "event")}</span>
                        </div>
                        <p>${escapeHtml(item.detail || "无详情")}</p>
                        <p class="muted-text">${escapeHtml(formatDateTime(item.created_at))}</p>
                    </li>
                `).join("")}
            </ul>
        `;
    }

    function renderDetail(detail) {
        const container = document.getElementById("user-detail-content");
        const user = detail.user;
        const payout = detail.payout_info;
        const stats = detail.assignment_stats;
        const tags = (user.tags || []).length ? user.tags.join(" / ") : "-";
        const reviewAt = user.reviewed_at ? formatDateTime(user.reviewed_at) : "-";
        const completeness = buildCompleteness(user, payout);

        const payoutHtml = payout
            ? `
                <div class="info-grid">
                    <div class="info-item"><span>收款方式</span><strong>${escapeHtml(payout.payout_method || "-")}</strong></div>
                    <div class="info-item"><span>收款户名</span><strong>${escapeHtml(payout.account_name || "-")}</strong></div>
                    <div class="info-item"><span>收款账号</span><strong>${escapeHtml(payout.account_no || "-")}</strong></div>
                    <div class="info-item"><span>备注</span><strong>${escapeHtml(payout.note || "-")}</strong></div>
                </div>
            `
            : `<div class="empty">该用户尚未提交收款信息</div>`;

        const completenessHtml = completeness.missing.length
            ? `
                <ul class="warning-list">
                    ${completeness.missing.map((label) => `<li>${escapeHtml(label)}待补全</li>`).join("")}
                </ul>
            `
            : `<p class="ok-text">资料完整，可直接进入审核结论阶段。</p>`;

        container.innerHTML = `
            <section class="module-card">
                <div class="detail-header">
                    <h3 class="detail-title">${escapeHtml(user.display_name || user.username || "-")}</h3>
                    <span class="status ${escapeHtml(user.review_status)}">${escapeHtml(reviewStatusLabel(user.review_status))}</span>
                </div>
                <div class="info-grid">
                    <div class="info-item"><span>用户ID</span><strong>${user.id}</strong></div>
                    <div class="info-item"><span>角色 / 状态</span><strong>${escapeHtml(roleLabel(user.role))} / ${user.is_active ? "启用" : "停用"}</strong></div>
                    <div class="info-item"><span>注册时间</span><strong>${escapeHtml(formatDateTime(user.created_at))}</strong></div>
                    <div class="info-item"><span>最近审核时间</span><strong>${escapeHtml(reviewAt)}</strong></div>
                    <div class="info-item"><span>邮箱</span><strong>${escapeHtml(user.email || "-")}</strong></div>
                    <div class="info-item"><span>手机号</span><strong>${escapeHtml(user.phone || "-")}</strong></div>
                    <div class="info-item"><span>实名 / 证件号</span><strong>${escapeHtml(user.real_name || "-")} / ${escapeHtml(maskIdNo(user.id_no))}</strong></div>
                    <div class="info-item"><span>城市 / 领域</span><strong>${escapeHtml(user.city || "-")} / ${escapeHtml(user.category || "-")}</strong></div>
                    <div class="info-item"><span>粉丝 / 均播</span><strong>${Number(user.follower_total || 0).toLocaleString("zh-CN")} / ${Number(user.avg_views || 0).toLocaleString("zh-CN")}</strong></div>
                    <div class="info-item"><span>标签</span><strong>${escapeHtml(tags)}</strong></div>
                    <div class="info-item"><span>上次审核结论</span><strong>${escapeHtml(user.review_reason || "-")}</strong></div>
                    <div class="info-item"><span>运营权重</span><strong>${Number(user.weight || 1).toFixed(2)}</strong></div>
                </div>

                <div class="row-actions">
                    ${userActions(user)}
                </div>

                <div class="weight-editor">
                    <input class="input" id="detail-weight-input" type="number" min="0.1" step="0.1" value="${Number(user.weight || 1).toFixed(1)}">
                    <button class="mini-btn primary" data-action="save-weight" data-user-id="${user.id}">更新运营权重</button>
                </div>
            </section>

            <section class="module-card">
                <h4>审核准备度</h4>
                <div class="completeness-head">
                    <span>资料完整度</span>
                    <strong>${completeness.percent}% (${completeness.done}/${completeness.total})</strong>
                </div>
                <div class="progress-track"><span style="width:${completeness.percent}%"></span></div>
                ${completenessHtml}
            </section>

            <section class="module-card">
                <h4>平台账号</h4>
                <ul class="stack-list">
                    ${renderAccountGroup("抖音", "douyin", user.douyin_accounts)}
                    ${renderAccountGroup("小红书", "xiaohongshu", user.xiaohongshu_accounts)}
                    ${renderAccountGroup("微博", "weibo", user.weibo_accounts)}
                </ul>
            </section>

            <section class="module-card">
                <h4>收款信息</h4>
                ${payoutHtml}
            </section>

            <section class="module-card">
                <h4>分配统计</h4>
                <div class="tiny-kpi">
                    <div class="box"><p class="label">总分配</p><p class="value">${stats.total}</p></div>
                    <div class="box"><p class="label">已完成</p><p class="value">${stats.completed}</p></div>
                    <div class="box"><p class="label">审核中</p><p class="value">${stats.in_review}</p></div>
                    <div class="box"><p class="label">已提交</p><p class="value">${stats.submitted}</p></div>
                    <div class="box"><p class="label">已拒绝</p><p class="value">${stats.rejected}</p></div>
                    <div class="box"><p class="label">累计收益</p><p class="value">¥${Number(stats.total_revenue || 0).toFixed(2)}</p></div>
                </div>
                <p class="muted-text">最近一次分配: ${escapeHtml(formatDateTime(stats.last_assignment_at))}</p>
            </section>

            <section class="module-card">
                <h4>最近分配</h4>
                ${renderAssignments(detail)}
            </section>

            <section class="module-card">
                <h4>最近行为日志</h4>
                ${renderActivities(detail)}
            </section>
        `;
    }

    async function loadUserDetail(userId, silent = false) {
        selectedUserId = userId;
        renderUsers();

        if (!silent) {
            document.getElementById("user-detail-content").innerHTML = `<div class="empty">正在加载用户详情...</div>`;
        }

        selectedDetail = await apiRequest(`/admin/users/${userId}/detail`);
        renderDetail(selectedDetail);
    }

    async function handleUserReview(userId, nextStatus) {
        let reviewReason = null;
        if (nextStatus === "rejected") {
            reviewReason = window.prompt("请输入驳回原因（必填）", "") || "";
            if (!reviewReason.trim()) {
                adminLayout.showAlert("驳回原因不能为空");
                return;
            }
        }

        await apiRequest(`/admin/users/${userId}/review`, {
            method: "PATCH",
            body: {
                review_status: nextStatus,
                review_reason: reviewReason ? reviewReason.trim() : null,
            },
        });

        await loadUsers(true, true);
        if (selectedUserId === userId) {
            await loadUserDetail(userId, true);
        }
        adminLayout.showAlert(`用户 ${userId} 审核状态已更新为 ${reviewStatusLabel(nextStatus)}`, "success");
    }

    async function handleWeightUpdate(userId) {
        const weightInput = document.getElementById("detail-weight-input");
        if (!weightInput) return;
        const weight = Number(weightInput.value || 0);
        if (!Number.isFinite(weight) || weight <= 0) {
            adminLayout.showAlert("权重必须为大于 0 的数字");
            return;
        }

        await apiRequest(`/admin/users/${userId}/weight`, {
            method: "PATCH",
            body: { weight },
        });

        await loadUsers(true, false);
        await loadUserDetail(userId, true);
        adminLayout.showAlert(`用户 ${userId} 权重已更新为 ${weight}`, "success");
    }

    async function loadUsers(preserveDetail = true, refreshSummary = true) {
        adminLayout.clearAlert();
        const statusFilter = document.getElementById("user-status-filter").value;
        const query = statusFilter === "all"
            ? "/admin/users?role=blogger"
            : `/admin/users?role=blogger&review_status=${encodeURIComponent(statusFilter)}`;

        const [userList, summary] = await Promise.all([
            apiRequest(query),
            refreshSummary ? apiRequest("/admin/users/review-summary") : Promise.resolve(reviewSummary),
        ]);

        users = userList;
        users.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

        if (summary) {
            reviewSummary = summary;
        }

        renderReviewSummary();
        renderUsers();
        adminLayout.setLastUpdated();

        if (!preserveDetail || !selectedUserId) return;
        const exists = users.some((item) => item.id === selectedUserId);
        if (exists) {
            await loadUserDetail(selectedUserId, true);
            return;
        }

        selectedUserId = null;
        selectedDetail = null;
        document.getElementById("user-detail-content").innerHTML = `<div class="empty">当前筛选条件下，已选用户不在列表中。</div>`;
    }

    async function onSummaryFilterClick(status) {
        const select = document.getElementById("user-status-filter");
        if (!select) return;

        select.value = status;
        await loadUsers(false, false);
    }

    function bindEvents() {
        document.getElementById("reload-users").addEventListener("click", async () => {
            try {
                await loadUsers(true, true);
                adminLayout.showAlert("审核列表已刷新", "success");
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新失败");
            }
        });

        document.getElementById("user-status-filter").addEventListener("change", async () => {
            try {
                await loadUsers(false, false);
            } catch (error) {
                adminLayout.showAlert(error.message || "加载用户失败");
            }
        });

        document.getElementById("user-search-input").addEventListener("input", () => {
            renderUsers();
        });

        document.getElementById("review-summary-grid").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-summary-status]");
            if (!button) return;

            button.disabled = true;
            try {
                await onSummaryFilterClick(button.dataset.summaryStatus);
            } catch (error) {
                adminLayout.showAlert(error.message || "切换筛选失败");
            } finally {
                button.disabled = false;
            }
        });

        document.getElementById("user-review-body").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-action]");
            if (button) {
                const action = button.dataset.action;
                const userId = Number(button.dataset.userId);
                if (!userId) return;

                button.disabled = true;
                try {
                    if (action === "open-detail") {
                        await loadUserDetail(userId);
                    } else if (action === "user-review") {
                        const nextStatus = button.dataset.next;
                        if (!nextStatus) return;
                        await handleUserReview(userId, nextStatus);
                    }
                } catch (error) {
                    adminLayout.showAlert(error.message || "操作失败");
                } finally {
                    button.disabled = false;
                }
                return;
            }

            const row = event.target.closest("tr[data-row-user-id]");
            if (!row) return;
            const userId = Number(row.dataset.rowUserId);
            if (!userId) return;

            try {
                await loadUserDetail(userId);
            } catch (error) {
                adminLayout.showAlert(error.message || "加载用户详情失败");
            }
        });

        document.getElementById("user-detail-panel").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-action]");
            if (!button) return;
            const action = button.dataset.action;
            const userId = Number(button.dataset.userId);
            if (!userId) return;

            button.disabled = true;
            try {
                if (action === "save-weight") {
                    await handleWeightUpdate(userId);
                } else if (action === "open-detail") {
                    await loadUserDetail(userId);
                } else if (action === "user-review") {
                    const nextStatus = button.dataset.next;
                    if (!nextStatus) return;
                    await handleUserReview(userId, nextStatus);
                }
            } catch (error) {
                adminLayout.showAlert(error.message || "操作失败");
            } finally {
                button.disabled = false;
            }
        });
    }

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            await adminLayout.init({ moduleLabel: "用户审核" });
            bindEvents();
            await loadUsers(false, true);
        } catch (error) {
            adminLayout.showAlert(error.message || "用户审核页面加载失败");
        }
    });
})();
