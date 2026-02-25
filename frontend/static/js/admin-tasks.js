(function () {
    let tasksForAdmin = [];

    function parseAttachmentUrls(raw) {
        return (raw || "")
            .split(/[\n,]/)
            .map((item) => item.trim())
            .filter((item) => /^https?:\/\/\S+$/i.test(item));
    }

    function setTaskOpResult(message) {
        const el = document.getElementById("task-op-result");
        if (!el) return;
        el.textContent = message;
    }

    async function uploadTaskAttachments(files) {
        const uploadedUrls = [];
        for (const file of files) {
            const formData = new FormData();
            formData.append("file", file);
            const result = await apiRequest("/admin/tasks/attachments/upload", {
                method: "POST",
                body: formData,
            });
            uploadedUrls.push(result.url);
        }
        return uploadedUrls;
    }

    function refreshTaskSelectOptions() {
        const select = document.getElementById("distribute-task-id");
        const publishedTasks = (tasksForAdmin || []).filter((task) => task.status === "published");
        select.innerHTML = publishedTasks
            .map((task) => `<option value="${task.id}">${escapeHtml(task.title)} (ID:${task.id})</option>`)
            .join("");

        if (!publishedTasks.length) {
            setTaskOpResult("当前没有已发布任务，请先创建并发布任务。");
        }
    }

    function renderTaskList() {
        const body = document.getElementById("task-list-body");
        if (!tasksForAdmin.length) {
            body.innerHTML = `<tr><td colspan="6" class="empty">当前暂无任务</td></tr>`;
            return;
        }

        body.innerHTML = tasksForAdmin.map((task) => `
            <tr>
                <td>${task.id}</td>
                <td>${escapeHtml(task.title || "-")}</td>
                <td>${escapeHtml(platformLabel(task.platform))}</td>
                <td><span class="status ${escapeHtml(task.status)}">${escapeHtml(task.status)}</span></td>
                <td>¥${Number(task.base_reward || 0).toFixed(2)}</td>
                <td>${escapeHtml(formatDateTime(task.created_at))}</td>
            </tr>
        `).join("");
    }

    function getSelectedTaskId() {
        const value = Number(document.getElementById("distribute-task-id").value);
        return Number.isInteger(value) && value > 0 ? value : null;
    }

    async function createTask() {
        const title = document.getElementById("task-title").value.trim();
        const description = document.getElementById("task-description").value.trim();
        const instructions = document.getElementById("task-instructions").value.trim();
        const platform = document.getElementById("task-platform").value;
        const status = document.getElementById("task-status").value;
        const baseReward = Number(document.getElementById("task-base-reward").value || 0);
        const attachmentInput = document.getElementById("task-attachments");
        const manualAttachmentUrls = parseAttachmentUrls(document.getElementById("task-attachment-urls").value);

        if (!title || !description || !instructions) {
            setTaskOpResult("创建失败: 标题、任务描述、执行要求均为必填。");
            return;
        }
        if (!Number.isFinite(baseReward) || baseReward < 0) {
            setTaskOpResult("创建失败: 基础奖励必须为大于等于 0 的数字。");
            return;
        }

        const files = Array.from(attachmentInput?.files || []);
        let uploadedUrls = [];
        if (files.length) {
            setTaskOpResult(`正在上传 ${files.length} 个附件...`);
            uploadedUrls = await uploadTaskAttachments(files);
        }

        const attachments = [...uploadedUrls, ...manualAttachmentUrls];
        const created = await apiRequest("/admin/tasks", {
            method: "POST",
            body: {
                title,
                description,
                platform,
                base_reward: baseReward,
                instructions,
                attachments,
                status,
            },
        });

        document.getElementById("task-title").value = "";
        document.getElementById("task-description").value = "";
        document.getElementById("task-instructions").value = "";
        document.getElementById("task-attachment-urls").value = "";
        if (attachmentInput) attachmentInput.value = "";

        await loadTasks();
        setTaskOpResult(`创建成功: 任务ID ${created.id}，状态 ${created.status}，附件 ${attachments.length} 个。`);
        adminLayout.showAlert("任务创建成功", "success");
    }

    async function viewEligibleBloggers() {
        const taskId = getSelectedTaskId();
        if (!taskId) {
            setTaskOpResult("请先选择任务。");
            return;
        }

        const limit = Number(document.getElementById("distribute-limit").value || 20);
        const bloggers = await apiRequest(`/admin/tasks/${taskId}/eligible-bloggers?limit=${limit}`);
        if (!bloggers.length) {
            setTaskOpResult("当前没有可分配候选达人。");
            return;
        }

        const lines = bloggers.slice(0, 40).map((item) => {
            const name = item.display_name || item.username;
            return `用户ID ${item.user_id} | ${name} | 粉丝 ${item.follower_total} | 均播 ${item.avg_views} | 权重 ${item.weight}`;
        });
        setTaskOpResult(`候选达人(${bloggers.length}):\n${lines.join("\n")}`);
    }

    async function autoDistributeTask() {
        const taskId = getSelectedTaskId();
        if (!taskId) {
            setTaskOpResult("请先选择任务。");
            return;
        }

        const limit = Number(document.getElementById("distribute-limit").value || 20);
        const result = await apiRequest(`/admin/tasks/${taskId}/distribute`, {
            method: "POST",
            body: { limit },
        });

        await loadTasks();
        setTaskOpResult(`自动分配完成: 新建 ${result.created_count} 条，跳过已存在 ${result.skipped_existing_count} 条。`);
        adminLayout.showAlert("自动分配已执行", "success");
    }

    async function manualDistributeTask() {
        const taskId = getSelectedTaskId();
        if (!taskId) {
            setTaskOpResult("请先选择任务。");
            return;
        }

        const raw = document.getElementById("distribute-user-ids").value.trim();
        const ids = raw
            .split(",")
            .map((item) => Number(item.trim()))
            .filter((item) => Number.isInteger(item) && item > 0);

        if (!ids.length) {
            setTaskOpResult("请填写有效用户ID列表。");
            return;
        }

        const result = await apiRequest(`/admin/tasks/${taskId}/distribute`, {
            method: "POST",
            body: { user_ids: ids, limit: ids.length },
        });

        await loadTasks();
        setTaskOpResult(`指定分配完成: 新建 ${result.created_count} 条，跳过已存在 ${result.skipped_existing_count} 条。`);
        adminLayout.showAlert("指定分配已执行", "success");
    }

    async function loadTasks(showSuccess = false) {
        adminLayout.clearAlert();
        tasksForAdmin = await apiRequest("/admin/tasks");
        tasksForAdmin.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        refreshTaskSelectOptions();
        renderTaskList();
        adminLayout.setLastUpdated();
        if (showSuccess) {
            adminLayout.showAlert("任务数据已刷新", "success");
        }
    }

    function bindEvents() {
        document.getElementById("refresh-tasks").addEventListener("click", async () => {
            try {
                await loadTasks(true);
            } catch (error) {
                adminLayout.showAlert(error.message || "刷新任务数据失败");
            }
        });

        document.getElementById("create-task-btn").addEventListener("click", async () => {
            try {
                await createTask();
            } catch (error) {
                setTaskOpResult(`创建失败: ${error.message || error}`);
            }
        });

        document.getElementById("view-eligible-btn").addEventListener("click", async () => {
            try {
                await viewEligibleBloggers();
            } catch (error) {
                setTaskOpResult(`查询失败: ${error.message || error}`);
            }
        });

        document.getElementById("auto-distribute-btn").addEventListener("click", async () => {
            try {
                await autoDistributeTask();
            } catch (error) {
                setTaskOpResult(`分配失败: ${error.message || error}`);
            }
        });

        document.getElementById("manual-distribute-btn").addEventListener("click", async () => {
            try {
                await manualDistributeTask();
            } catch (error) {
                setTaskOpResult(`分配失败: ${error.message || error}`);
            }
        });
    }

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            await adminLayout.init({ moduleLabel: "任务分配" });
            bindEvents();
            await loadTasks();
        } catch (error) {
            adminLayout.showAlert(error.message || "任务运营页面加载失败");
        }
    });
})();
