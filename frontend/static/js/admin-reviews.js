(function () {
    let reviewAssignments = [];
    let pendingManualSubmissions = [];

    function renderAssignmentReviewQueue() {
        const body = document.getElementById("assignment-review-body");
        if (!reviewAssignments.length) {
            body.innerHTML = `<tr><td colspan="7" class="empty">当前没有待审核作业</td></tr>`;
            return;
        }

        body.innerHTML = reviewAssignments.map((assignment) => {
            const actions = [];
            const manualReady = assignment.metric_sync_status === "manual_approved";
            if (assignment.status === "submitted") {
                actions.push(`<button class="mini-btn primary" data-action="assignment-start-review" data-assignment-id="${assignment.id}">进入审核</button>`);
            }
            if (manualReady) {
                actions.push(`<button class="mini-btn success" data-action="assignment-approve" data-assignment-id="${assignment.id}">通过</button>`);
            } else {
                actions.push(`<button class="mini-btn muted" disabled title="需先手工指标审核通过">待手工通过</button>`);
            }
            actions.push(`<button class="mini-btn danger" data-action="assignment-reject" data-assignment-id="${assignment.id}">驳回</button>`);

            return `
                <tr>
                    <td>${assignment.id}</td>
                    <td>${escapeHtml(assignment.task?.title || "-")}</td>
                    <td><span class="status ${escapeHtml(assignment.status)}">${escapeHtml(assignmentStatusLabel(assignment.status))}</span></td>
                    <td>${assignment.post_link ? `<a href="${escapeHtml(assignment.post_link)}" target="_blank" rel="noopener noreferrer">查看链接</a>` : "-"}</td>
                    <td><span class="status ${escapeHtml(assignment.metric_sync_status)}">${escapeHtml(metricSyncStatusLabel(assignment.metric_sync_status))}</span></td>
                    <td>¥${Number(assignment.revenue || 0).toFixed(2)}</td>
                    <td><div class="actions">${actions.join("")}</div></td>
                </tr>
            `;
        }).join("");
    }

    function renderManualReviewQueue() {
        const body = document.getElementById("manual-review-body");
        if (!pendingManualSubmissions.length) {
            body.innerHTML = `<tr><td colspan="6" class="empty">当前没有待审核手工指标</td></tr>`;
            return;
        }

        body.innerHTML = pendingManualSubmissions.map((item) => `
            <tr>
                <td>${item.id}</td>
                <td>${item.assignment_id}</td>
                <td>赞 ${item.likes} / 评 ${item.comments} / 转 ${item.shares} / 播 ${item.views}</td>
                <td>${escapeHtml(item.note || "-")}</td>
                <td>${escapeHtml(formatDateTime(item.submitted_at))}</td>
                <td>
                    <div class="actions">
                        <button class="mini-btn success" data-action="manual-approve" data-submission-id="${item.id}">通过</button>
                        <button class="mini-btn danger" data-action="manual-reject" data-submission-id="${item.id}">驳回</button>
                    </div>
                </td>
            </tr>
        `).join("");
    }

    async function handleAssignmentReview(action, assignmentId) {
        if (action === "assignment-start-review") {
            await apiRequest(`/admin/assignments/${assignmentId}/start-review`, { method: "POST" });
            await loadReviewQueues();
            adminLayout.showAlert(`分配 ${assignmentId} 已进入审核中`, "success");
            return;
        }

        if (action === "assignment-approve") {
            const assignment = reviewAssignments.find((item) => item.id === assignmentId);
            if (assignment && assignment.metric_sync_status !== "manual_approved") {
                adminLayout.showAlert(`分配 ${assignmentId} 尚未完成手工数据审核，不能通过`);
                return;
            }
            await apiRequest(`/admin/assignments/${assignmentId}/approve`, { method: "POST" });
            await loadReviewQueues();
            adminLayout.showAlert(`分配 ${assignmentId} 已审核通过`, "success");
            return;
        }

        if (action === "assignment-reject") {
            const reason = window.prompt("请输入驳回原因（必填）", "") || "";
            if (!reason.trim()) {
                adminLayout.showAlert("驳回原因不能为空");
                return;
            }
            await apiRequest(`/admin/assignments/${assignmentId}/reject`, {
                method: "POST",
                body: { reason: reason.trim() },
            });
            await loadReviewQueues();
            adminLayout.showAlert(`分配 ${assignmentId} 已驳回`, "success");
        }
    }

    async function handleManualReview(submissionId, approved) {
        let reviewReason = null;
        if (!approved) {
            reviewReason = window.prompt("请输入驳回原因（必填）", "") || "";
            if (!reviewReason.trim()) {
                adminLayout.showAlert("驳回原因不能为空");
                return;
            }
        }

        await apiRequest(`/admin/manual-metrics/${submissionId}/review`, {
            method: "POST",
            body: {
                approved,
                review_reason: reviewReason ? reviewReason.trim() : null,
            },
        });
        await loadReviewQueues();
        adminLayout.showAlert(`手工指标记录 ${submissionId} 已${approved ? "通过" : "驳回"}`, "success");
    }

    async function loadReviewQueues(showSuccess = false) {
        adminLayout.clearAlert();
        const [submittedAssignments, inReviewAssignments, manualPending] = await Promise.all([
            apiRequest("/admin/assignments?status=submitted"),
            apiRequest("/admin/assignments?status=in_review"),
            apiRequest("/admin/manual-metrics/pending"),
        ]);

        reviewAssignments = [...(submittedAssignments || []), ...(inReviewAssignments || [])]
            .sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
        pendingManualSubmissions = manualPending || [];

        renderAssignmentReviewQueue();
        renderManualReviewQueue();
        adminLayout.setLastUpdated();

        if (showSuccess) {
            adminLayout.showAlert("审核队列已刷新", "success");
        }
    }

    function bindEvents() {
        document.getElementById("refresh-reviews").addEventListener("click", async () => {
            try {
                await loadReviewQueues(true);
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新审核数据失败");
            }
        });

        document.getElementById("reload-assignments").addEventListener("click", async () => {
            try {
                await loadReviewQueues(true);
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新作业队列失败");
            }
        });

        document.getElementById("reload-manual").addEventListener("click", async () => {
            try {
                await loadReviewQueues(true);
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新手工指标队列失败");
            }
        });

        document.getElementById("assignment-review-body").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-action]");
            if (!button) return;
            const action = button.dataset.action;
            const assignmentId = Number(button.dataset.assignmentId);
            if (!assignmentId) return;

            button.disabled = true;
            try {
                await handleAssignmentReview(action, assignmentId);
            } catch (error) {
                adminLayout.showAlert(error.message || "审核作业失败");
            } finally {
                button.disabled = false;
            }
        });

        document.getElementById("manual-review-body").addEventListener("click", async (event) => {
            const button = event.target.closest("button[data-action]");
            if (!button) return;
            const action = button.dataset.action;
            const submissionId = Number(button.dataset.submissionId);
            if (!submissionId) return;

            button.disabled = true;
            try {
                if (action === "manual-approve") {
                    await handleManualReview(submissionId, true);
                }
                if (action === "manual-reject") {
                    await handleManualReview(submissionId, false);
                }
            } catch (error) {
                adminLayout.showAlert(error.message || "审核手工指标失败");
            } finally {
                button.disabled = false;
            }
        });
    }

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            await adminLayout.init({ moduleLabel: "作业审核" });
            bindEvents();
            await loadReviewQueues();
        } catch (error) {
            adminLayout.showAlert(error.message || "审核中心加载失败");
        }
    });
})();
