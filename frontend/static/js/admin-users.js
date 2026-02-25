(function () {
    let users = [];
    let selectedUserId = null;
    let selectedDetail = null;
    let reviewSummary = null;
    let detailModalEl = null;
    let detailContentEl = null;

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

    function buildCompleteness(user) {
        const checks = [
            { label: "实名信息", ok: Boolean(user.real_name && user.id_no) },
            { label: "联系方式", ok: Boolean(user.phone) },
            { label: "城市与领域", ok: Boolean(user.city && user.category) },
            { label: "至少 1 个社媒账号", ok: socialAccountCount(user) > 0 },
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

    function userActions(user, options = {}) {
        const includeOpenDetail = options.includeOpenDetail !== false;
        const actions = [];

        if (includeOpenDetail) {
            actions.push(`<button class="mini-btn muted" data-action="open-detail" data-user-id="${user.id}">查看详情</button>`);
        }

        if (user.review_status === "pending") {
            actions.push(`<button class="mini-btn primary" data-action="user-review" data-next="under_review" data-user-id="${user.id}">进入审核</button>`);
        } else if (user.review_status === "under_review") {
            actions.push(`<button class="mini-btn success" data-action="user-review" data-next="approved" data-user-id="${user.id}">通过</button>`);
            actions.push(`<button class="mini-btn danger" data-action="user-review" data-next="rejected" data-user-id="${user.id}">驳回</button>`);
        } else if (user.review_status === "rejected") {
            actions.push(`<button class="mini-btn warning" data-action="user-review" data-next="under_review" data-user-id="${user.id}">重新审核</button>`);
        } else if (user.review_status === "approved") {
            actions.push(`<button class="mini-btn warning" data-action="user-review" data-next="under_review" data-user-id="${user.id}">回退审核中</button>`);
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
            body.innerHTML = `<tr><td colspan="6" class="empty">当前筛选条件下无可展示达人</td></tr>`;
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
        if (!detailContentEl) return;

        const user = detail.user;
        const tags = (user.tags || []).length ? user.tags.join(" / ") : "-";
        const reviewAt = user.reviewed_at ? formatDateTime(user.reviewed_at) : "-";
        const completeness = buildCompleteness(user);

        const completenessHtml = completeness.missing.length
            ? `
                <ul class="warning-list">
                    ${completeness.missing.map((label) => `<li>${escapeHtml(label)}待补全</li>`).join("")}
                </ul>
            `
            : `<p class="ok-text">资料完整，可进入下一步审核动作。</p>`;

        detailContentEl.innerHTML = `
            <div class="detail-modal-grid">
                <section class="module-card">
                    <div class="detail-header">
                        <h3 class="detail-title">${escapeHtml(user.display_name || user.username || "-")}</h3>
                        <span class="status ${escapeHtml(user.review_status)}">${escapeHtml(reviewStatusLabel(user.review_status))}</span>
                    </div>
                    <div class="info-grid">
                        <div class="info-item"><span>达人ID</span><strong>${user.id}</strong></div>
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
                    <h4>最近行为日志</h4>
                    ${renderActivities(detail)}
                </section>
            </div>
        `;
    }

    function isDetailModalOpen() {
        return Boolean(detailModalEl && detailModalEl.classList.contains("is-open"));
    }

    function openDetailModal() {
        if (!detailModalEl) return;
        detailModalEl.classList.add("is-open");
        detailModalEl.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
    }

    function closeDetailModal() {
        if (!detailModalEl) return;
        detailModalEl.classList.remove("is-open");
        detailModalEl.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
    }

    async function ensureDetailModal() {
        if (detailModalEl && detailContentEl) return;

        const existingModal = document.getElementById("user-detail-modal");
        const existingContent = document.getElementById("user-detail-content");
        if (existingModal && existingContent) {
            detailModalEl = existingModal;
            detailContentEl = existingContent;
            return;
        }

        let templateHtml = "";
        try {
            const resp = await fetch("/static/templates/admin-user-detail-modal.html", {
                method: "GET",
                cache: "no-store",
            });
            if (resp.ok) {
                templateHtml = await resp.text();
            }
        } catch (error) {
            console.warn("load modal template failed", error);
        }

        if (!templateHtml.trim()) {
            templateHtml = `
                <div class="modal-backdrop" id="user-detail-modal" aria-hidden="true">
                    <div class="modal-dialog detail-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="user-detail-modal-title">
                        <div class="modal-header">
                            <h3 class="modal-title" id="user-detail-modal-title">达人详情</h3>
                            <button type="button" class="modal-close" aria-label="关闭" data-action="close-user-detail-modal">&times;</button>
                        </div>
                        <div id="user-detail-content" class="modal-body muted-text">请先选择达人查看详情。</div>
                    </div>
                </div>
            `;
        }

        document.body.insertAdjacentHTML("beforeend", templateHtml);
        detailModalEl = document.getElementById("user-detail-modal");
        detailContentEl = document.getElementById("user-detail-content");
        if (!detailModalEl || !detailContentEl) {
            throw new Error("详情弹窗模板加载失败");
        }
    }

    async function loadUserDetail(userId, silent = false) {
        await ensureDetailModal();
        selectedUserId = userId;
        renderUsers();
        openDetailModal();

        if (!silent && detailContentEl) {
            detailContentEl.innerHTML = `<div class="empty">正在加载达人详情...</div>`;
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
        if (selectedUserId === userId && isDetailModalOpen()) {
            await loadUserDetail(userId, true);
        }
        adminLayout.showAlert(`达人 ${userId} 审核状态已更新为 ${reviewStatusLabel(nextStatus)}`, "success");
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
        if (exists && isDetailModalOpen()) {
            await loadUserDetail(selectedUserId, true);
            return;
        }

        if (!exists) {
            selectedUserId = null;
            selectedDetail = null;
            if (isDetailModalOpen() && detailContentEl) {
                closeDetailModal();
            }
        }
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
                adminLayout.showAlert("达人列表已刷新", "success");
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新失败");
            }
        });

        document.getElementById("user-status-filter").addEventListener("change", async () => {
            try {
                await loadUsers(false, false);
            } catch (error) {
                adminLayout.showAlert(error.message || "加载达人失败");
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
                adminLayout.showAlert(error.message || "加载达人详情失败");
            }
        });

        if (detailModalEl) {
            detailModalEl.addEventListener("click", (event) => {
                if (event.target === detailModalEl) {
                    closeDetailModal();
                    return;
                }

                const button = event.target.closest("button[data-action]");
                if (!button) return;

                const action = button.dataset.action;
                if (action === "close-user-detail-modal") {
                    closeDetailModal();
                }
            });
        }

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && isDetailModalOpen()) {
                closeDetailModal();
            }
        });
    }

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            await adminLayout.init({ moduleLabel: "达人审核" });
            await ensureDetailModal();
            bindEvents();
            await loadUsers(false, true);
        } catch (error) {
            adminLayout.showAlert(error.message || "达人审核页面加载失败");
        }
    });
})();
