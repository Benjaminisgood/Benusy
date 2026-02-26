const API_PREFIX = "/api/v1";

function getToken() {
    return localStorage.getItem("access_token") || sessionStorage.getItem("access_token");
}

function clearAuth() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("token_type");
    localStorage.removeItem("current_user_role");
    localStorage.removeItem("current_user_name");
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("token_type");
    sessionStorage.removeItem("current_user_role");
    sessionStorage.removeItem("current_user_name");
}

function requireAuthRedirect() {
    const token = getToken();
    if (!token) {
        window.location.href = "/login";
        return null;
    }
    return token;
}

function roleLabel(role) {
    if (role === "admin") return "管理员";
    if (role === "blogger") return "博主达人";
    return role || "-";
}

function platformLabel(platform) {
    const value = (platform || "").toLowerCase();
    if (value === "douyin" || value === "抖音" || value === "dy") return "抖音";
    if (value === "xiaohongshu" || value === "小红书" || value === "xhs") return "小红书";
    if (value === "weibo" || value === "微博" || value === "wb") return "微博";
    return platform || "-";
}

function assignmentStatusLabel(status) {
    const map = {
        accepted: "待提交",
        in_review: "审核中",
        rejected: "已拒绝",
        completed: "已完成",
        cancelled: "已取消",
    };
    return map[status] || status || "-";
}

function metricSyncStatusLabel(status) {
    const map = {
        normal: "自动预采集成功（待手工确认）",
        manual_required: "自动采集异常（需手工补录）",
        manual_pending_review: "手工数据待审核",
        manual_approved: "手工数据已通过",
        manual_rejected: "手工数据被驳回",
    };
    return map[status] || status || "-";
}

function formatDateTime(iso) {
    if (!iso) return "-";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;
    return date.toLocaleString("zh-CN", { hour12: false });
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function detailToMessage(detail, fallback) {
    if (!detail) return fallback;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
        return detail
            .map((item) => {
                if (typeof item === "string") return item;
                if (item && typeof item === "object" && item.msg) return item.msg;
                return JSON.stringify(item);
            })
            .join("; ");
    }
    if (typeof detail === "object" && detail.msg) return detail.msg;
    return fallback;
}

async function apiRequest(path, options = {}) {
    const {
        method = "GET",
        body = undefined,
        headers = {},
        auth = true,
    } = options;

    const requestHeaders = new Headers(headers);
    if (auth) {
        const token = requireAuthRedirect();
        if (!token) {
            throw new Error("未登录");
        }
        requestHeaders.set("Authorization", `Bearer ${token}`);
    }

    let requestBody = body;
    if (body !== undefined && !(body instanceof FormData)) {
        if (!requestHeaders.has("Content-Type")) {
            requestHeaders.set("Content-Type", "application/json");
        }
        if (requestHeaders.get("Content-Type") === "application/json" && typeof body !== "string") {
            requestBody = JSON.stringify(body);
        }
    }

    const response = await fetch(`${API_PREFIX}${path}`, {
        method,
        headers: requestHeaders,
        body: requestBody,
    });

    let payload = null;
    if (response.status !== 204) {
        payload = await response.json().catch(() => null);
    }

    if (response.status === 401) {
        clearAuth();
        window.location.href = "/login";
        throw new Error("登录已失效");
    }

    if (!response.ok) {
        throw new Error(detailToMessage(payload?.detail, `请求失败 (${response.status})`));
    }

    return payload;
}

function homeRouteByRole(role) {
    if (role === "admin") return "/admin/dashboard";
    return "/dashboard";
}

function redirectByRole(role) {
    window.location.href = homeRouteByRole(role);
}

async function requireUserWithRoles(allowedRoles) {
    const user = await apiRequest("/users/me");
    if (Array.isArray(allowedRoles) && allowedRoles.length > 0 && !allowedRoles.includes(user.role)) {
        redirectByRole(user.role);
        throw new Error("无权限访问当前页面");
    }
    return user;
}
