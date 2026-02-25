(function () {
    let overview = null;
    let selectedUserId = null;
    let selectedDetail = null;
    let searchTimer = null;

    const modalEl = document.getElementById("settlement-detail-modal");
    const modalContentEl = document.getElementById("settlement-detail-content");

    function payoutMethodLabel(method) {
        const map = {
            bank_card: "银行卡",
            wechat_pay: "微信支付",
            alipay: "支付宝",
            paypal: "PayPal",
            other: "其他",
        };
        return map[method] || method || "-";
    }

    function reviewStatusLabel(status) {
        const map = {
            pending: "待审核",
            under_review: "审核中",
            approved: "已通过",
            rejected: "已驳回",
        };
        return map[status] || status || "-";
    }

    function settlementStatusLabel(status) {
        const map = {
            pending: "待结款",
            partially_paid: "部分已结",
            paid_off: "已结清",
            no_revenue: "暂无收益",
        };
        return map[status] || status || "-";
    }

    function settlementStatusClass(status) {
        if (status === "paid_off") return "approved";
        if (status === "partially_paid") return "under_review";
        if (status === "pending") return "pending";
        return "rejected";
    }

    function money(value) {
        return `¥${Number(value || 0).toFixed(2)}`;
    }

    function renderOverview() {
        if (!overview) return;

        document.getElementById("set-kpi-bloggers").textContent = String(overview.blogger_count || 0);
        document.getElementById("set-kpi-total-revenue").textContent = money(overview.total_revenue || 0);
        document.getElementById("set-kpi-total-settled").textContent = money(overview.total_settled || 0);
        document.getElementById("set-kpi-total-pending").textContent = money(overview.total_pending || 0);

        const rows = overview.users || [];
        const body = document.getElementById("settlement-body");
        if (!rows.length) {
            body.innerHTML = `<tr><td colspan="7" class="empty">当前条件下无可展示达人</td></tr>`;
        } else {
            body.innerHTML = rows.map((item) => `
                <tr data-user-id="${item.user_id}" data-pending="${Number(item.pending_settlement || 0).toFixed(2)}">
                    <td>
                        <strong>${escapeHtml(item.display_name || item.username || "-")}</strong><br>
                        <span class="muted-text">@${escapeHtml(item.username || "-")}</span><br>
                        <span class="muted-text">${escapeHtml(item.phone || "-")} / ${escapeHtml(item.city || "-")}</span>
                    </td>
                    <td>${escapeHtml(payoutMethodLabel(item.preferred_method))}</td>
                    <td>${money(item.total_revenue)}</td>
                    <td>${money(item.total_settled)}</td>
                    <td>${money(item.pending_settlement)}</td>
                    <td>
                        <span class="status ${escapeHtml(settlementStatusClass(item.settlement_status))}">
                            ${escapeHtml(settlementStatusLabel(item.settlement_status))}
                        </span>
                    </td>
                    <td>
                        <div class="row-actions">
                            <button class="mini-btn primary" data-action="open-detail" data-user-id="${item.user_id}">查看详情</button>
                            <button class="mini-btn warning" data-action="edit-weight" data-user-id="${item.user_id}">更新权重</button>
                            <button class="mini-btn success" data-action="create-record" data-user-id="${item.user_id}">登记放款</button>
                        </div>
                    </td>
                </tr>
            `).join("");
        }

        adminLayout.setLastUpdated(overview.generated_at);
    }

    function payoutInfoHtml(payout) {
        if (!payout) {
            return `<div class="empty">该达人尚未填写收款信息</div>`;
        }

        const method = payout.payout_method;
        if (method === "wechat_pay") {
            return `
                <div class="info-grid">
                    <div class="info-item"><span>首选方式</span><strong>微信支付</strong></div>
                    <div class="info-item"><span>微信号</span><strong>${escapeHtml(payout.wechat_id || "-")}</strong></div>
                    <div class="info-item"><span>手机号</span><strong>${escapeHtml(payout.wechat_phone || "-")}</strong></div>
                    <div class="info-item"><span>收款码</span><strong>${payout.wechat_qr_url ? `<a href="${escapeHtml(payout.wechat_qr_url)}" target="_blank" rel="noopener noreferrer">查看收款码</a>` : "-"}</strong></div>
                </div>
                <p class="muted-text">备注: ${escapeHtml(payout.note || "-")}</p>
            `;
        }

        if (method === "alipay") {
            return `
                <div class="info-grid">
                    <div class="info-item"><span>首选方式</span><strong>支付宝</strong></div>
                    <div class="info-item"><span>收款人姓名</span><strong>${escapeHtml(payout.alipay_account_name || "-")}</strong></div>
                    <div class="info-item"><span>手机号</span><strong>${escapeHtml(payout.alipay_phone || "-")}</strong></div>
                    <div class="info-item"><span>收款码</span><strong>${payout.alipay_qr_url ? `<a href="${escapeHtml(payout.alipay_qr_url)}" target="_blank" rel="noopener noreferrer">查看收款码</a>` : "-"}</strong></div>
                </div>
                <p class="muted-text">备注: ${escapeHtml(payout.note || "-")}</p>
            `;
        }

        return `
            <div class="info-grid">
                <div class="info-item"><span>首选方式</span><strong>${escapeHtml(payoutMethodLabel(method))}</strong></div>
                <div class="info-item"><span>银行卡说明</span><strong>${escapeHtml(payout.bank_description || "请线下确认收款银行卡并执行放款")}</strong></div>
            </div>
            <p class="muted-text">备注: ${escapeHtml(payout.note || "-")}</p>
        `;
    }

    function recordsHtml(records) {
        if (!records.length) {
            return `<div class="empty">暂无结款记录</div>`;
        }
        return `
            <div class="table-wrap">
                <table>
                    <thead>
                    <tr>
                        <th>记录ID</th>
                        <th>金额</th>
                        <th>放款时间</th>
                        <th>备注</th>
                        <th>操作人</th>
                    </tr>
                    </thead>
                    <tbody>
                    ${records.map((item) => `
                        <tr>
                            <td>${item.id}</td>
                            <td>${money(item.amount)}</td>
                            <td>${escapeHtml(formatDateTime(item.paid_at))}</td>
                            <td>${escapeHtml(item.note || "-")}</td>
                            <td>${escapeHtml(String(item.admin_id || "-"))}</td>
                        </tr>
                    `).join("")}
                    </tbody>
                </table>
            </div>
        `;
    }

    function activitiesHtml(activities) {
        if (!activities.length) {
            return `<div class="empty">暂无行为日志</div>`;
        }
        return `
            <ul class="stack-list">
                ${activities.map((item) => `
                    <li class="stack-item">
                        <div class="stack-item-head">
                            <h5>${escapeHtml(item.title || item.action_type || "-")}</h5>
                            <span class="activity-tag">${escapeHtml(item.action_type || "event")}</span>
                        </div>
                        <p>${escapeHtml(item.detail || "-")}</p>
                        <p class="muted-text">${escapeHtml(formatDateTime(item.created_at))}</p>
                    </li>
                `).join("")}
            </ul>
        `;
    }

    function renderDetail() {
        if (!selectedDetail) return;
        const detail = selectedDetail;
        const user = detail.user;
        const summary = detail.summary;
        const payout = detail.payout_info;
        const records = detail.recent_records || [];
        const activities = detail.recent_activities || [];
        const payoutReadyText = summary.has_valid_payout_info ? "可放款" : "收款信息待补全";

        modalContentEl.innerHTML = `
            <div class="detail-modal-grid">
                <section class="module-card">
                    <div class="detail-header">
                        <h3 class="detail-title">${escapeHtml(user.display_name || user.username || "-")}</h3>
                        <span class="status ${escapeHtml(settlementStatusClass(summary.settlement_status))}">
                            ${escapeHtml(settlementStatusLabel(summary.settlement_status))}
                        </span>
                    </div>
                    <div class="info-grid">
                        <div class="info-item"><span>达人ID</span><strong>${user.id}</strong></div>
                        <div class="info-item"><span>用户名</span><strong>${escapeHtml(user.username || "-")}</strong></div>
                        <div class="info-item"><span>手机号</span><strong>${escapeHtml(user.phone || "-")}</strong></div>
                        <div class="info-item"><span>审核状态</span><strong>${escapeHtml(reviewStatusLabel(user.review_status))}</strong></div>
                        <div class="info-item"><span>可结算收益</span><strong>${money(summary.total_revenue)}</strong></div>
                        <div class="info-item"><span>已结款</span><strong>${money(summary.total_settled)}</strong></div>
                        <div class="info-item"><span>待结款</span><strong>${money(summary.pending_settlement)}</strong></div>
                        <div class="info-item"><span>收款信息</span><strong>${escapeHtml(payoutReadyText)}</strong></div>
                        <div class="info-item"><span>运营权重</span><strong>${Number(user.weight || 1).toFixed(2)}</strong></div>
                    </div>
                </section>

                <section class="module-card">
                    <h4>收款信息</h4>
                    ${payoutInfoHtml(payout)}
                </section>

                <section class="module-card">
                    <h4>结款记录</h4>
                    ${recordsHtml(records)}
                </section>

                <section class="module-card">
                    <h4>最近行为日志</h4>
                    ${activitiesHtml(activities)}
                </section>
            </div>
        `;
    }

    function openModal() {
        modalEl.classList.add("is-open");
        modalEl.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
    }

    function closeModal() {
        modalEl.classList.remove("is-open");
        modalEl.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
    }

    async function loadOverview(showSuccess = false) {
        const statusFilter = document.getElementById("settlement-status-filter").value;
        const keyword = (document.getElementById("settlement-search-input").value || "").trim();
        const params = new URLSearchParams();
        if (statusFilter && statusFilter !== "all") {
            params.set("status", statusFilter);
        }
        if (keyword) {
            params.set("keyword", keyword);
        }
        const query = params.toString() ? `?${params.toString()}` : "";
        overview = await apiRequest(`/admin/settlements/summary${query}`);
        renderOverview();
        if (showSuccess) {
            adminLayout.showAlert("收益结款数据已刷新", "success");
        }
    }

    async function loadDetail(userId, silent = false) {
        selectedUserId = userId;
        openModal();
        if (!silent) {
            modalContentEl.innerHTML = `<div class="empty">正在加载达人结款详情...</div>`;
        }
        selectedDetail = await apiRequest(`/admin/settlements/${userId}`);
        renderDetail();
    }

    async function handleUpdateWeight(userId) {
        if (!userId) return;

        let currentWeight = null;
        if (selectedDetail && selectedDetail.user && Number(selectedDetail.user.id) === userId) {
            currentWeight = Number(selectedDetail.user.weight || 1);
        } else {
            const detail = await apiRequest(`/admin/settlements/${userId}`);
            currentWeight = Number(detail?.user?.weight || 1);
        }
        if (!Number.isFinite(currentWeight) || currentWeight <= 0) {
            currentWeight = 1;
        }

        const raw = window.prompt("请输入新的运营权重（大于 0）", currentWeight.toFixed(1));
        if (raw === null) return;
        const value = Number(String(raw).trim());
        if (!Number.isFinite(value) || value <= 0) {
            adminLayout.showAlert("权重必须为大于 0 的数字");
            return;
        }

        await apiRequest(`/admin/users/${userId}/weight`, {
            method: "PATCH",
            body: { weight: value },
        });

        await loadOverview(false);
        if (selectedUserId === userId && modalEl.classList.contains("is-open")) {
            await loadDetail(userId, true);
        }
        adminLayout.showAlert("运营权重已更新", "success");
    }

    async function handleCreateRecord(userId, pendingAmount) {
        if (!userId) return;
        const pending = Number(pendingAmount || 0);
        const amountRaw = window.prompt(
            pending > 0 ? `请输入放款金额（当前待结款 ${money(pending)}）` : "请输入放款金额（元）",
            pending > 0 ? pending.toFixed(2) : "",
        );
        if (amountRaw === null) return;

        const amount = Number(String(amountRaw).trim());
        if (!Number.isFinite(amount) || amount <= 0) {
            adminLayout.showAlert("请填写正确的放款金额");
            return;
        }
        const noteRaw = window.prompt("请输入备注（可选）", "");
        const note = noteRaw === null ? null : String(noteRaw).trim() || null;

        await apiRequest(`/admin/settlements/${userId}/records`, {
            method: "POST",
            body: {
                amount,
                note,
            },
        });

        await loadOverview(false);
        if (selectedUserId === userId && modalEl.classList.contains("is-open")) {
            await loadDetail(userId, true);
        }
        adminLayout.showAlert("放款记录已登记", "success");
    }

    function bindEvents() {
        document.getElementById("reload-settlements").addEventListener("click", async () => {
            try {
                await loadOverview(true);
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新结款数据失败");
            }
        });

        document.getElementById("settlement-status-filter").addEventListener("change", async () => {
            try {
                await loadOverview(false);
            } catch (error) {
                adminLayout.showAlert(error.message || "加载结款数据失败");
            }
        });

        document.getElementById("settlement-search-input").addEventListener("input", () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(async () => {
                try {
                    await loadOverview(false);
                } catch (error) {
                    adminLayout.showAlert(error.message || "检索达人失败");
                }
            }, 350);
        });

        document.getElementById("settlement-body").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-action]");
            if (button) {
                const action = button.dataset.action;
                const userId = Number(button.dataset.userId);
                const row = button.closest("tr[data-user-id]");
                const pending = Number(row?.dataset.pending || 0);
                if (!userId) return;

                button.disabled = true;
                try {
                    if (action === "open-detail") {
                        await loadDetail(userId);
                    } else if (action === "edit-weight") {
                        await handleUpdateWeight(userId);
                    } else if (action === "create-record") {
                        await handleCreateRecord(userId, pending);
                    }
                } catch (error) {
                    adminLayout.showAlert(error.message || "操作失败");
                } finally {
                    button.disabled = false;
                }
                return;
            }

            const row = event.target.closest("tr[data-user-id]");
            if (!row) return;
            const userId = Number(row.dataset.userId);
            if (!userId) return;

            try {
                await loadDetail(userId);
            } catch (error) {
                adminLayout.showAlert(error.message || "加载结款详情失败");
            }
        });

        modalEl.addEventListener("click", (event) => {
            if (event.target === modalEl || event.target.closest("[data-action='close-settlement-detail']")) {
                closeModal();
            }
        });

    }

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            await adminLayout.init({ moduleLabel: "收益结款" });
            bindEvents();
            await loadOverview(false);
        } catch (error) {
            adminLayout.showAlert(error.message || "收益结款模块加载失败");
        }
    });
})();
