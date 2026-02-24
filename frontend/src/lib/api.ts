import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";

// ─── Axios Instance ──────────────────────────────────────────────────────────

const api = axios.create({
    baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
    timeout: 30000,
    headers: {
        "Content-Type": "application/json",
    },
});

// ─── Request Interceptor: attach JWT token ───────────────────────────────────

api.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
        const token = localStorage.getItem("token");
        if (token && config.headers) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error: AxiosError) => {
        return Promise.reject(error);
    }
);

// ─── Response Interceptor: centralized error handling ────────────────────────

api.interceptors.response.use(
    (response) => response,
    (error: AxiosError<{ detail?: string }>) => {
        if (error.response) {
            const { status } = error.response;

            if (status === 401) {
                // Token expired or invalid — clear auth and redirect
                localStorage.removeItem("token");
                // Only redirect if not already on auth pages
                if (!window.location.pathname.startsWith("/login") &&
                    !window.location.pathname.startsWith("/register")) {
                    window.location.href = "/login";
                }
            }

            if (status === 403) {
                console.error("Access denied: insufficient permissions");
            }

            if (status >= 500) {
                console.error("Server error — please try again later");
            }

            // Surface the backend error message
            const detail = error.response.data?.detail;
            if (detail) {
                error.message = detail;
            }
        } else if (error.request) {
            error.message = "Network error — server may be unavailable";
        }

        return Promise.reject(error);
    }
);

export default api;
