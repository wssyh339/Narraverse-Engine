import axios from "axios";
import type { ApiErrorPayload, ApiResponse } from "../types/api";

const fallbackApiBaseUrl = "http://localhost:8000/api";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || fallbackApiBaseUrl
).replace(/\/$/, "");

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
});

export class ApiClientError extends Error {
  code: ApiErrorPayload["code"];
  details: unknown;
  requestId: string;
  status: number;

  constructor(payload: ApiErrorPayload, requestId: string, status: number) {
    super(payload.message);
    this.name = "ApiClientError";
    this.code = payload.code;
    this.details = payload.details;
    this.requestId = requestId;
    this.status = status;
  }
}

export function isApiClientError(value: unknown): value is ApiClientError {
  return value instanceof ApiClientError;
}

export async function requestJson<TData>(
  path: string,
  init: RequestInit = {},
): Promise<TData> {
  try {
    const response = await api.request<ApiResponse<TData>>({
      url: path,
      method: init.method ?? "GET",
      data: init.body ? JSON.parse(String(init.body)) : undefined,
      headers: init.headers as Record<string, string> | undefined,
    });
    const payload = response.data;
    if (!payload.success || payload.error || payload.data === null) {
      throw new ApiClientError(
        payload.error ?? {
          code: "INTERNAL_ERROR",
          message: "后端返回了无法识别的响应。",
          details: payload,
        },
        payload.request_id,
        response.status,
      );
    }
    return payload.data;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (axios.isAxiosError(error) && error.response?.data) {
      const payload = error.response.data as ApiResponse<TData>;
      if (payload.error) {
        throw new ApiClientError(payload.error, payload.request_id, error.response.status);
      }
    }
    throw new ApiClientError(
      {
        code: "INTERNAL_ERROR",
        message: "无法连接后端服务，请确认 http://localhost:8000 已启动。",
        details: {},
      },
      "req_unavailable",
      0,
    );
  }
}

export async function unwrap<TData>(promise: Promise<{ data: ApiResponse<TData> }>): Promise<TData> {
  try {
    const response = await promise;
    const payload = response.data;
    if (!payload.success || payload.error || payload.data === null) {
      throw new ApiClientError(
        payload.error ?? {
          code: "INTERNAL_ERROR",
          message: "后端返回了无法识别的响应。",
          details: payload,
        },
        payload.request_id,
        200,
      );
    }
    return payload.data;
  } catch (error) {
    if (error instanceof ApiClientError) {
      throw error;
    }
    if (axios.isAxiosError(error) && error.response?.data) {
      const payload = error.response.data as ApiResponse<TData>;
      if (payload.error) {
        throw new ApiClientError(payload.error, payload.request_id, error.response.status);
      }
    }
    throw new ApiClientError(
      {
        code: "INTERNAL_ERROR",
        message: "无法连接后端服务，请确认 http://localhost:8000 已启动。",
        details: {},
      },
      "req_unavailable",
      0,
    );
  }
}
