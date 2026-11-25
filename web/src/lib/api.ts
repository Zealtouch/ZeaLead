// Backend client. In production the FastAPI server serves this UI and /api on one origin;
// in development `next dev` proxies /api to it (next.config.mjs).

import { t } from "@/i18n";
import { auth } from "@/lib/auth";
import type {
  ActivityRow,
  AgentInfo,
  Badges,
  Brief,
  Community,
  CommunityRow,
  Company,
  Dashboard,
  GraphEdge,
  GraphNode,
  Intent,
  Lead,
  LeadDetail,
  LeadStats,
  LeadStatus,
  LLMCallDetail,
  LLMCallRow,
  LogRow,
  NodeDetail,
  Page,
  PlatformInfo,
  Run,
  RunMessage,
  SettingsResp,
  SystemInfo,
  Task,
  TaskDetail,
  ToolCallDetail,
  ToolCallRow,
  Usage,
  User,
} from "@/lib/types";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const token = auth.getToken();
  const r = await fetch(`/api${path}`, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  if (r.status === 401 && !path.startsWith("/auth/")) {
    if (typeof window !== "undefined") {
      auth.clearToken();
      window.location.href = "/login";
    }
    throw new ApiError(t("Sign in required"), 401);
  }
  if (!r.ok) {
    let message = `${init?.method ?? "GET"} ${path}: ${r.status}`;
    try {
      const payload = (await r.json()) as { error?: unknown };
      if (typeof payload.error === "string" && payload.error.trim()) message = payload.error.trim();
    } catch {
      /* keep the status-based message */
    }
    throw new ApiError(message, r.status);
  }
  if (r.status === 204) return undefined as T;
  return r.json();
}

// qs builds a query string, dropping empty values.
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    p.set(k, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : "";
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
});

// download fetches an authenticated file and hands it to the browser.
async function download(path: string, filename: string): Promise<void> {
  const token = auth.getToken();
  const r = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!r.ok) throw new ApiError(`${path}: ${r.status}`, r.status);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

type Scope = { company?: string | number };

export const api = {
  // auth
  health: () => http<{ ok: boolean; version: string }>("/health"),
  authStatus: () => http<{ setup_required: boolean; version: string }>("/auth/status"),
  setup: (username: string, password: string) =>
    http<{ token: string; user: User }>("/auth/setup", json("POST", { username, password })),
  login: (username: string, password: string) =>
    http<{ token: string; user: User }>("/auth/login", json("POST", { username, password })),
  me: () => http<User>("/auth/me"),
  changePassword: (current: string, next: string) =>
    http<{ token: string; user: User }>("/auth/password", json("POST", { current, new: next })),
  badges: () => http<Badges>("/badges"),

  // users (admin)
  users: () => http<User[]>("/users"),
  createUser: (username: string, password: string, role: string) =>
    http<{ id: number }>("/users", json("POST", { username, password, role })),
  updateUser: (id: number, body: { role?: string; password?: string }) => http(`/users/${id}`, json("PATCH", body)),
  deleteUser: (id: number) => http(`/users/${id}`, json("DELETE")),

  // companies
  companies: () => http<Company[]>("/companies"),
  createCompany: (body: { name: string; website?: string; description?: string }) =>
    http<{ id: number }>("/companies", json("POST", body)),
  updateCompany: (id: number, body: { name: string; website?: string; description?: string }) =>
    http(`/companies/${id}`, json("PUT", body)),
  deleteCompany: (id: number) => http(`/companies/${id}`, json("DELETE")),

  // dashboard
  dashboard: (s: Scope = {}) => http<Dashboard>(`/dashboard${qs(s)}`),

  // tasks
  tasks: (s: Scope = {}) => http<Task[]>(`/campaigns${qs(s)}`),
  task: (id: number) => http<TaskDetail>(`/campaigns/${id}`),
  createTask: (body: { brief?: Partial<Brief>; brief_yaml?: string; company_id?: number | null; start?: boolean }) =>
    http<{ id: number }>("/campaigns", json("POST", body)),
  updateBrief: (id: number, body: { brief?: Partial<Brief>; brief_yaml?: string }) =>
    http(`/campaigns/${id}/brief`, json("PUT", body)),
  setTaskCompany: (id: number, companyId: number | null) =>
    http(`/campaigns/${id}/company`, json("PUT", { company_id: companyId })),
  startTask: (id: number) => http(`/campaigns/${id}/start`, json("POST")),
  pauseTask: (id: number) => http(`/campaigns/${id}/pause`, json("POST")),
  deleteTask: (id: number) => http(`/campaigns/${id}`, json("DELETE")),
  addHint: (id: number, text: string) => http<{ id: number }>(`/campaigns/${id}/hints`, json("POST", { text })),
  intents: (id: number) => http<Intent[]>(`/campaigns/${id}/intents`),
  sessions: (id: number) => http<{ runs: Run[]; usage: Usage; running: boolean }>(`/campaigns/${id}/sessions`),
  runMessages: (runId: number, after = 0) =>
    http<{ run: Run; messages: RunMessage[] }>(`/runs/${runId}/messages${qs({ after })}`),
  activity: (id: number, after = 0) => http<ActivityRow[]>(`/campaigns/${id}/activity${qs({ after })}`),
  graph: (id: number) => http<{ nodes: GraphNode[]; edges: GraphEdge[] }>(`/campaigns/${id}/graph`),
  taskCommunities: (id: number) => http<CommunityRow[]>(`/campaigns/${id}/communities`),
  node: (id: number) => http<NodeDetail>(`/nodes/${id}`),
  downloadReport: (id: number) => download(`/campaigns/${id}/report.html`, `leadscout-task-${id}-report.html`),
  briefTemplate: () => http<{ yaml: string }>("/brief-template"),

  // leads
  leads: (p: {
    company?: string | number;
    campaign?: number;
    level?: string;
    status?: string;
    platform?: string;
    q?: string;
    sort?: string;
    offset?: number;
    limit?: number;
  }) => http<Page<Lead>>(`/leads${qs(p)}`),
  leadStats: (p: { company?: string | number; campaign?: number } = {}) => http<LeadStats>(`/leads/stats${qs(p)}`),
  lead: (id: number) => http<LeadDetail>(`/leads/${id}`),
  setLeadStatus: (id: number, status: LeadStatus) => http(`/leads/${id}`, json("PATCH", { status })),
  editMessages: (id: number, body: { suggested_reply?: string; dm_message?: string }) =>
    http(`/leads/${id}`, json("PATCH", body)),
  draftLead: (id: number, instruction?: string) =>
    http<LeadDetail>(`/leads/${id}/draft`, json("POST", instruction ? { instruction } : {})),
  draftTaskMessages: (id: number) => http<{ queued: number }>(`/campaigns/${id}/draft-messages`, json("POST")),
  downloadLeads: (p: Record<string, string | number | undefined>) => download(`/leads.csv${qs(p)}`, "leadscout-leads.csv"),

  // communities and records
  communities: (p: { company?: string | number; platform?: string; q?: string; offset?: number; limit?: number }) =>
    http<Page<Community>>(`/communities${qs(p)}`),
  toolCalls: (p: {
    company?: string | number;
    campaign?: number;
    tool?: string;
    errors?: boolean;
    run?: number;
    offset?: number;
    limit?: number;
  }) => http<Page<ToolCallRow> & { tools: string[] }>(`/tool-calls${qs(p)}`),
  toolCall: (id: number) => http<ToolCallDetail>(`/tool-calls/${id}`),
  llmCalls: (p: {
    company?: string | number;
    campaign?: number;
    role?: string;
    model?: string;
    offset?: number;
    limit?: number;
  }) =>
    http<
      Page<LLMCallRow> & {
        totals: { i: number; o: number; cr: number; cw: number };
        models: string[];
        by_model: { model: string; calls: number; i: number; o: number; cr: number }[];
      }
    >(`/llm-calls${qs(p)}`),
  llmCall: (id: number) => http<LLMCallDetail>(`/llm-calls/${id}`),
  logs: (p: {
    company?: string | number;
    campaign?: number;
    role?: string;
    kind?: string;
    q?: string;
    offset?: number;
    limit?: number;
  }) => http<Page<LogRow>>(`/logs${qs(p)}`),
  activityDetail: (id: number) => http<ActivityRow & { detail: string | null }>(`/activity/${id}`),

  // system
  settings: () => http<SettingsResp>("/settings"),
  saveSettings: (body: Record<string, string | number | null>) =>
    http<{ ok: boolean; note: string }>("/settings", json("PUT", body)),
  platforms: () => http<PlatformInfo[]>("/system/platforms"),
  agents: () => http<AgentInfo[]>("/system/agents"),
  systemInfo: () => http<SystemInfo>("/system/info"),
};
