(function () {
    let tasksForAdmin = [];
    let editingTaskId = null;
    let estimateRequestVersion = 0;
    let estimateDebounceTimer = null;

    const ESTIMATE_PREVIEW_LIMIT = 12;
    const ESTIMATE_DEBOUNCE_MS = 260;

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

    function setTaskEstimateResult(message) {
        const el = document.getElementById("task-estimate-result");
        if (!el) return;
        el.textContent = message;
    }

    function setEstimateMetricValue(elementId, value) {
        const el = document.getElementById(elementId);
        if (!el) return;
        el.textContent = value;
    }

    function resetEstimateMetrics() {
        setEstimateMetricValue("estimate-platform-value", "-");
        setEstimateMetricValue("estimate-eligible-count", "-");
        setEstimateMetricValue("estimate-accept-count", "-");
        setEstimateMetricValue("estimate-saturation-rate", "-");
        setEstimateMetricValue("estimate-recommended-scale", "-");
    }

    function applyEstimateSummary(summary, warningMessage = "") {
        const eligibleCount = Number(summary.eligible_count || 0);
        const estimatedAcceptCount = Number(summary.estimated_accept_count || 0);
        const inputAcceptLimit = Number.isInteger(summary.input_accept_limit)
            ? summary.input_accept_limit
            : null;
        const platformText = platformLabel(summary.platform);
        const saturationRateRaw = Number(summary.saturation_rate || 0);
        const saturationRate = Number.isFinite(saturationRateRaw) ? saturationRateRaw : 0;
        const saturationLabel = String(summary.saturation_label || "");
        const recommendedScaleMin = Number(summary.recommended_scale_min || 0);
        const recommendedScaleMax = Number(summary.recommended_scale_max || 0);
        const saturationPercent = `${(saturationRate * 100).toFixed(1)}%`;
        const recommendedScaleText = recommendedScaleMax <= 0
            ? "暂无建议"
            : (recommendedScaleMin > 0 && recommendedScaleMin !== recommendedScaleMax)
                ? `${recommendedScaleMin}-${recommendedScaleMax} 人`
                : `${recommendedScaleMax} 人`;

        setEstimateMetricValue("estimate-platform-value", platformText);
        setEstimateMetricValue("estimate-eligible-count", `${eligibleCount} 人`);
        setEstimateMetricValue("estimate-accept-count", `${estimatedAcceptCount} 人`);
        setEstimateMetricValue("estimate-saturation-rate", saturationPercent);
        setEstimateMetricValue("estimate-recommended-scale", recommendedScaleText);

        const lines = (summary.preview_bloggers || []).slice(0, 40).map((item) => {
            const name = item.display_name || item.username;
            return `用户ID ${item.user_id} | ${name} | 粉丝 ${item.follower_total} | 均播 ${item.avg_views} | 权重 ${item.weight}`;
        });

        const notes = [];
        if (warningMessage) {
            notes.push(warningMessage);
        }
        if (eligibleCount <= 0) {
            notes.push("当前平台暂无可接单达人，建议先补充达人池再发布任务。");
        } else if (inputAcceptLimit === null) {
            notes.push(`当前未设置接单上限，按全量开放估算（预计饱和度 ${saturationPercent}）。`);
            notes.push(`建议首轮投放规模控制在 ${recommendedScaleText}，后续按完成率滚动加量。`);
        } else {
            notes.push(`当前接单上限 ${inputAcceptLimit} 人，预计可接单 ${estimatedAcceptCount} 人（饱和度 ${saturationPercent}，${saturationLabel}）。`);
            if (recommendedScaleMax > 0 && inputAcceptLimit < recommendedScaleMin) {
                notes.push(`当前上限偏保守，建议提升至 ${recommendedScaleText} 以扩大覆盖。`);
            } else if (recommendedScaleMax > 0 && inputAcceptLimit > recommendedScaleMax) {
                notes.push(`当前上限偏激进，建议先按 ${recommendedScaleText} 分批放量。`);
            } else if (recommendedScaleMax > 0) {
                notes.push(`当前上限处于建议区间（${recommendedScaleText}），可按当前节奏发布。`);
            }
        }

        const previewHeader = lines.length
            ? `预览前 ${Math.min(lines.length, Number(summary.preview_limit) || ESTIMATE_PREVIEW_LIMIT)} 位候选达人:`
            : "暂无候选达人预览。";
        const previewBlock = lines.length ? `\n${lines.join("\n")}` : "";
        setTaskEstimateResult(
            `候选达人总数: ${eligibleCount}（平台: ${platformText}）\n${notes.join("\n")}\n${previewHeader}${previewBlock}`
        );
    }

    function parseAcceptLimitForEstimate() {
        const raw = document.getElementById("task-accept-limit")?.value.trim() || "";
        if (!raw) {
            return { acceptLimit: null, warningMessage: "" };
        }

        const parsed = Number(raw);
        if (!Number.isInteger(parsed) || parsed < 1 || parsed > 50000) {
            return { acceptLimit: null, warningMessage: "接单人数上限输入无效，当前按“不限人数”估算。" };
        }
        return { acceptLimit: parsed, warningMessage: "" };
    }

    function buildEstimateQueryString() {
        const platform = document.getElementById("task-platform")?.value || "douyin";
        const { acceptLimit, warningMessage } = parseAcceptLimitForEstimate();
        const params = new URLSearchParams();
        params.set("platform", platform);
        params.set("preview_limit", String(ESTIMATE_PREVIEW_LIMIT));
        if (Number.isInteger(acceptLimit)) {
            params.set("accept_limit", String(acceptLimit));
        }
        return {
            queryString: params.toString(),
            warningMessage,
        };
    }

    async function refreshDynamicEstimate() {
        const requestVersion = ++estimateRequestVersion;
        const { queryString, warningMessage } = buildEstimateQueryString();
        setTaskEstimateResult("正在根据当前输入更新预估...");

        try {
            const summary = await apiRequest(`/admin/tasks/eligible-bloggers-estimate?${queryString}`);
            if (requestVersion !== estimateRequestVersion) {
                return;
            }
            applyEstimateSummary(summary, warningMessage);
        } catch (error) {
            if (requestVersion !== estimateRequestVersion) {
                return;
            }
            resetEstimateMetrics();
            setTaskEstimateResult(`预估失败: ${error.message || error}`);
        }
    }

    function scheduleDynamicEstimate(delay = ESTIMATE_DEBOUNCE_MS) {
        if (estimateDebounceTimer) {
            window.clearTimeout(estimateDebounceTimer);
        }
        const wait = Math.max(0, Number(delay) || 0);
        estimateDebounceTimer = window.setTimeout(() => {
            refreshDynamicEstimate().catch(() => {
                setTaskEstimateResult("预估失败: 请求异常。");
            });
        }, wait);
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

    function clearTaskForm() {
        document.getElementById("task-title").value = "";
        document.getElementById("task-description").value = "";
        document.getElementById("task-instructions").value = "";
        document.getElementById("task-platform").value = "douyin";
        document.getElementById("task-status").value = "published";
        document.getElementById("task-base-reward").value = "100";
        document.getElementById("task-accept-limit").value = "";
        document.getElementById("task-attachment-urls").value = "";
        const attachmentInput = document.getElementById("task-attachments");
        if (attachmentInput) attachmentInput.value = "";
        scheduleDynamicEstimate(0);
    }

    function setEditingState(task) {
        const banner = document.getElementById("task-editing-banner");
        const saveBtn = document.getElementById("create-task-btn");
        const cancelBtn = document.getElementById("cancel-edit-task-btn");

        if (!task) {
            editingTaskId = null;
            banner.style.display = "none";
            banner.textContent = "";
            saveBtn.textContent = "创建任务";
            cancelBtn.style.display = "none";
            return;
        }

        editingTaskId = task.id;
        banner.style.display = "block";
        banner.textContent = `当前正在续写任务 #${task.id}（${task.status}）: ${task.title || "未命名任务"}`;
        saveBtn.textContent = "保存修改";
        cancelBtn.style.display = "inline-block";
    }

    function loadTaskToForm(task) {
        document.getElementById("task-title").value = task.title || "";
        document.getElementById("task-description").value = task.description || "";
        document.getElementById("task-instructions").value = task.instructions || "";
        document.getElementById("task-platform").value = task.platform || "douyin";
        document.getElementById("task-status").value = task.status || "draft";
        document.getElementById("task-base-reward").value = Number(task.base_reward || 0);
        document.getElementById("task-accept-limit").value = Number.isInteger(task.accept_limit) ? String(task.accept_limit) : "";
        document.getElementById("task-attachment-urls").value = (task.attachments || []).join("\n");
        const attachmentInput = document.getElementById("task-attachments");
        if (attachmentInput) attachmentInput.value = "";
        setEditingState(task);
        setTaskOpResult(`已加载任务 #${task.id}，可继续编辑后点击“保存修改”。`);
        scheduleDynamicEstimate(0);
    }

    function renderTaskList() {
        const body = document.getElementById("task-list-body");
        if (!tasksForAdmin.length) {
            body.innerHTML = `<tr><td colspan="9" class="empty">当前暂无任务</td></tr>`;
            return;
        }

        body.innerHTML = tasksForAdmin.map((task) => {
            const canResume = task.status === "draft";
            const acceptLimitText = Number.isInteger(task.accept_limit) ? `${task.accept_limit} 人` : "不限";
            const acceptedCount = Number(task.accepted_count || 0);
            const acceptedAndLimitText = Number.isInteger(task.accept_limit)
                ? `${acceptedCount}/${task.accept_limit}`
                : `${acceptedCount}/不限`;
            return `
                <tr>
                    <td>${task.id}</td>
                    <td>${escapeHtml(task.title || "-")}</td>
                    <td>${escapeHtml(platformLabel(task.platform))}</td>
                    <td><span class="status ${escapeHtml(task.status)}">${escapeHtml(task.status)}</span></td>
                    <td>¥${Number(task.base_reward || 0).toFixed(2)}</td>
                    <td>${escapeHtml(acceptLimitText)}</td>
                    <td>${escapeHtml(acceptedAndLimitText)}</td>
                    <td>${escapeHtml(formatDateTime(task.created_at))}</td>
                    <td>
                        <div class="row-actions">
                            <button class="mini-btn ${canResume ? "primary" : "muted"}" data-action="resume-task" data-task-id="${task.id}">
                                ${canResume ? "续写草稿" : "查看并编辑"}
                            </button>
                        </div>
                    </td>
                </tr>
            `;
        }).join("");
    }

    function collectTaskFormData() {
        const title = document.getElementById("task-title").value.trim();
        const description = document.getElementById("task-description").value.trim();
        const instructions = document.getElementById("task-instructions").value.trim();
        const platform = document.getElementById("task-platform").value;
        const status = document.getElementById("task-status").value;
        const baseReward = Number(document.getElementById("task-base-reward").value || 0);
        const acceptLimitRaw = document.getElementById("task-accept-limit").value.trim();
        let acceptLimit = null;

        if (!title || !description || !instructions) {
            throw new Error("标题、任务描述、执行要求均为必填。");
        }
        if (!Number.isFinite(baseReward) || baseReward < 0) {
            throw new Error("基础奖励必须为大于等于 0 的数字。");
        }
        if (acceptLimitRaw) {
            const parsed = Number(acceptLimitRaw);
            if (!Number.isInteger(parsed) || parsed < 1 || parsed > 50000) {
                throw new Error("接单人数上限必须是 1-50000 的整数，留空表示不限。");
            }
            acceptLimit = parsed;
        }

        return {
            title,
            description,
            platform,
            base_reward: baseReward,
            accept_limit: acceptLimit,
            instructions,
            status,
        };
    }

    async function createOrUpdateTask() {
        const attachmentInput = document.getElementById("task-attachments");
        const manualAttachmentUrls = parseAttachmentUrls(document.getElementById("task-attachment-urls").value);
        const payload = collectTaskFormData();

        const files = Array.from(attachmentInput?.files || []);
        let uploadedUrls = [];
        if (files.length) {
            setTaskOpResult(`正在上传 ${files.length} 个附件...`);
            uploadedUrls = await uploadTaskAttachments(files);
        }
        payload.attachments = [...uploadedUrls, ...manualAttachmentUrls];

        if (editingTaskId) {
            const updated = await apiRequest(`/admin/tasks/${editingTaskId}`, {
                method: "PATCH",
                body: payload,
            });
            await loadTasks();
            setTaskOpResult(`保存成功: 任务ID ${updated.id}，状态 ${updated.status}，附件 ${payload.attachments.length} 个。`);
            adminLayout.showAlert("草稿已更新，可继续复用", "success");
            return;
        }

        const created = await apiRequest("/admin/tasks", {
            method: "POST",
            body: payload,
        });
        clearTaskForm();
        await loadTasks();
        setTaskOpResult(`创建成功: 任务ID ${created.id}，状态 ${created.status}，附件 ${payload.attachments.length} 个。`);
        adminLayout.showAlert("任务创建成功", "success");
    }

    async function loadTasks(showSuccess = false) {
        adminLayout.clearAlert();
        tasksForAdmin = await apiRequest("/admin/tasks");
        tasksForAdmin.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
        renderTaskList();

        if (editingTaskId) {
            const current = tasksForAdmin.find((task) => task.id === editingTaskId);
            if (!current) {
                setEditingState(null);
                clearTaskForm();
            } else {
                setEditingState(current);
            }
        }

        adminLayout.setLastUpdated();
        if (showSuccess) {
            adminLayout.showAlert("任务数据已刷新", "success");
        }
    }

    function bindEstimateInputs() {
        const inputIds = [
            "task-platform",
            "task-accept-limit",
        ];

        inputIds.forEach((id) => {
            const el = document.getElementById(id);
            if (!el) return;
            const eventName = el.tagName === "SELECT" ? "change" : "input";
            el.addEventListener(eventName, () => {
                scheduleDynamicEstimate();
            });
        });
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
                await createOrUpdateTask();
            } catch (error) {
                setTaskOpResult(`保存失败: ${error.message || error}`);
            }
        });

        document.getElementById("cancel-edit-task-btn").addEventListener("click", () => {
            setEditingState(null);
            clearTaskForm();
            setTaskOpResult("已退出续写模式，可继续新建任务。");
        });

        document.getElementById("task-list-body").addEventListener("click", (event) => {
            const button = event.target.closest("button[data-action='resume-task']");
            if (!button) return;

            const taskId = Number(button.dataset.taskId);
            const task = tasksForAdmin.find((item) => item.id === taskId);
            if (!task) {
                setTaskOpResult(`未找到任务 #${taskId}，请刷新后重试。`);
                return;
            }

            loadTaskToForm(task);
            window.scrollTo({ top: 0, behavior: "smooth" });
        });

        bindEstimateInputs();
    }

    document.addEventListener("DOMContentLoaded", async () => {
        try {
            resetEstimateMetrics();
            await adminLayout.init({ moduleLabel: "任务运营" });
            bindEvents();
            await loadTasks();
            scheduleDynamicEstimate(0);
        } catch (error) {
            adminLayout.showAlert(error.message || "任务运营页面加载失败");
        }
    });
})();
