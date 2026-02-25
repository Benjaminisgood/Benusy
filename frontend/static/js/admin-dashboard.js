(function () {
    let adminSummary = null;

    function renderSummary() {
        if (!adminSummary) return;

        document.getElementById("kpi-pending-users").textContent = String(adminSummary.review_queue.pending_users || 0);
        document.getElementById("kpi-under-review-users").textContent = String(adminSummary.review_queue.under_review_users || 0);
        document.getElementById("kpi-pending-assignments").textContent = String(adminSummary.review_queue.pending_assignment_reviews || 0);
        document.getElementById("kpi-pending-manual").textContent = String(adminSummary.review_queue.pending_manual_metric_reviews || 0);
        document.getElementById("kpi-published-tasks").textContent = String(adminSummary.task_stats.published || 0);
        document.getElementById("kpi-total-revenue").textContent = `¥${Number(adminSummary.revenue.total_revenue || 0).toFixed(2)}`;

        const formulas = adminSummary.formulas || [];
        const formulaList = document.getElementById("formula-list");
        formulaList.innerHTML = formulas.length
            ? formulas.map((item) => `
                <li class="formula-item">
                    <strong>${escapeHtml(item.label)}</strong>
                    <p>${escapeHtml(item.definition)}</p>
                </li>
            `).join("")
            : `<li class="formula-item"><strong>暂无定义</strong><p>后端未返回统计口径定义。</p></li>`;

        const activities = adminSummary.recent_activities || [];
        const activitiesBody = document.getElementById("recent-activities-body");
        activitiesBody.innerHTML = activities.length
            ? activities.map((item) => `
                <tr>
                    <td>${item.assignment_id}</td>
                    <td>${escapeHtml(item.task_title || "-")}</td>
                    <td>${escapeHtml(item.user_name || (item.user_id ? `用户${item.user_id}` : "-"))}</td>
                    <td><span class="status ${escapeHtml(item.status)}">${escapeHtml(assignmentStatusLabel(item.status))}</span></td>
                    <td>${escapeHtml(formatDateTime(item.created_at))}</td>
                </tr>
            `).join("")
            : `<tr><td colspan="5" class="empty">暂无动态记录</td></tr>`;

        adminLayout.setLastUpdated(adminSummary.generated_at);
    }

    async function loadDashboard(showSuccess = false) {
        adminLayout.clearAlert();
        adminSummary = await apiRequest("/admin/dashboard");
        renderSummary();
        if (showSuccess) {
            adminLayout.showAlert("总览数据已刷新", "success");
        }
    }

    function bindEventHandlers() {
        const refreshButton = document.getElementById("refresh-all");
        if (!refreshButton) return;
        refreshButton.addEventListener("click", async () => {
            try {
                await loadDashboard(true);
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新总览失败");
            }
        });
    }

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            await adminLayout.init({ moduleLabel: "总览" });
            bindEventHandlers();
            await loadDashboard();
        } catch (error) {
            adminLayout.showAlert(error.message || "总览加载失败");
        }
    });
})();
