// ZeaLead domain model — the shapes the FastAPI backend (zealead/server.py) returns.

export type LeadLevel = "hot" | "warm" | "cold";
export type LeadStatus = "new" | "contacted" | "replied" | "won" | "dismissed";
export type TaskStatus = "created" | "running" | "paused" | "done" | "failed" | "stopped";
export type NodeKind = "goal" | "intent" | "fact" | "lead" | "hint";

export interface User {
  id: number;
  username: string;
  role: "admin" | "member";
  created_at: number;
  last_login_at: number | null;
}

export interface Company {
  id: number;
  name: string;
  website: string | null;
  description: string | null;
  created_at: number;
  tasks: number;
  leads: number;
}

export interface Goal {
  id: number;
  text: string;
  state: "open" | "met" | "abandoned";
  have: number;
  target: number;
  min_intent: LeadLevel;
}

export interface LeadCounts {
  hot: number;
  warm: number;
  cold: number;
  by_platform: Record<string, Partial<Record<LeadLevel, number>>>;
}

export interface Task {
  id: number;
  name: string;
  status: TaskStatus;
  end_reason: string | null;
  created_at: number;
  updated_at: number;
  running_here: boolean;
  runner: string | null;
  company_id: number | null;
  company_name: string | null;
  product: string | null;
  goals: Goal[];
  leads: LeadCounts;
  intents: Record<"open" | "running" | "done" | "exhausted" | "blocked", number>;
  tokens: number;
}

export interface Brief {
  name: string;
  product: string;
  url?: string;
  description: string;
  ideal_customer: string;
  pain_points: string[];
  competitors: string[];
  keywords: string[];
  platforms: string[];
  exclude_platforms: string[];
  recency_days: number;
  objective?: string;
  target_leads: number;
  notes?: string;
  outreach?: { sender?: string; tone?: string; offer?: string };
  [k: string]: unknown;
}

export interface Usage {
  i: number;
  o: number;
  cr: number;
  cw: number;
  calls: number;
}

export interface TaskDetail extends Task {
  brief: Brief;
  constraints: { kind: "allow" | "deny"; text: string }[];
  todos: { content: string; status: "pending" | "in_progress" | "completed" }[];
  usage: Usage;
  coverage: Record<string, number>;
  hints: { id: number; text: string; state: string; created_at: number }[];
  platform_yield: Record<string, { intents: number; leads: number }>;
}

export interface Intent {
  id: number;
  state: string;
  owner: string | null;
  summary: string;
  platform: string | null;
  goal_id: number | null;
  leads: number;
  facts: number;
  tokens: number;
  created_at: number;
  updated_at: number;
}

export interface Run {
  id: number;
  campaign_id: number;
  role: "decomposer" | "planner" | "worker" | "writer";
  intent_id: number | null;
  model: string;
  title: string | null;
  state: "running" | "done" | "exhausted" | "error" | "stopped";
  error: string | null;
  started_at: number;
  ended_at: number | null;
  input_tokens: number;
  output_tokens: number;
  cache_read: number;
  tool_calls: number;
}

export type Block =
  | { type: "text"; text: string }
  | { type: "thinking"; text: string }
  | { type: "tool_use"; id: string; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; tool_use_id: string; content: string; is_error: boolean };

export interface RunMessage {
  id: number;
  role: "user" | "assistant" | "tool";
  content: Block[];
  ts: number;
}

export interface ActivityRow {
  id: number;
  intent_id: number | null;
  role: string;
  kind: string;
  summary: string;
  ts: number;
}

export interface GraphNode {
  id: number;
  kind: NodeKind;
  state: string;
  summary: string;
  platform: string | null;
}

export interface GraphEdge {
  source: number;
  target: number;
  rel: "spawns" | "derived_from" | "yields" | "proves";
}

export interface NodeRef {
  id: number;
  kind: string;
  summary: string;
}

export interface Source {
  id: number;
  kind: string;
  platform: string;
  key: string;
  title: string | null;
  url: string | null;
}

export interface Evidence {
  quote: string;
  url: string;
  platform: string;
  posted_at: number | null;
  text: string;
}

export interface Lead {
  node_id: number;
  campaign_id: number;
  campaign_name?: string;
  company_id?: number | null;
  dedup_key: string;
  platform: string;
  author: string | null;
  author_url: string | null;
  url: string;
  quote: string;
  posted_at: number | null;
  intent_level: LeadLevel;
  fit_score: number;
  pain: string | null;
  reason: string | null;
  suggested_reply: string | null; // public reply to post in their thread (draft)
  dm_message: string | null; // private message to the same person (draft)
  message_angle: string | null; // the personal hook the writer used
  message_note: string | null; // why a message was skipped
  drafted_at: number | null;
  message_edited: number;
  status: LeadStatus;
  created_at: number;
}

export interface LeadDetail extends Lead {
  evidence: Evidence[];
  payload: Record<string, unknown>;
  producers: number[];
}

export interface NodeDetail {
  id: number;
  campaign_id: number;
  kind: NodeKind;
  state: string;
  payload: Record<string, unknown>;
  origin: string | null;
  owner: string | null;
  created_at: number;
  updated_at: number;
  parents: NodeRef[];
  yields: NodeRef[];
  sources: Source[];
  worker_output?: string;
  runs?: Run[];
  lead?: Lead;
  evidence?: Evidence[];
}

export interface CommunityRow {
  id: number;
  platform: string;
  key: string;
  url: string | null;
  targeted: number;
  mined: number;
  leads: number;
  facts: number;
}

export interface Community {
  id: number;
  platform: string;
  key: string;
  title: string | null;
  url: string | null;
  first_seen: number;
  campaigns: number;
  leads: number;
  facts: number;
  intents: number;
  mined: number;
}

export interface LeadStats {
  total: number;
  hot: number;
  warm: number;
  cold: number;
  new: number;
  contacted: number;
  replied: number;
  won: number;
  dismissed: number;
  platforms: Record<string, number>;
}

export interface Dashboard {
  tasks: Record<string, number>;
  leads: LeadStats;
  series: { date: string; hot: number; warm: number; cold: number; tokens: number }[];
  tokens: Usage;
  tool_calls: { total: number; errors: number };
  recent_leads: Lead[];
  top_communities: { platform: string; key: string; url: string | null; leads: number }[];
  running: { id: number; name: string }[];
}

export interface Page<T> {
  items: T[];
  total: number;
}

export interface ToolCallRow {
  id: number;
  campaign_id: number;
  campaign_name: string;
  run_id: number | null;
  intent_id: number | null;
  role: string;
  tool: string;
  input: string;
  is_error: number;
  duration_ms: number;
  output_len: number | null;
  ts: number;
}

export interface ToolCallDetail extends Omit<ToolCallRow, "input" | "output_len"> {
  input: Record<string, unknown>;
  output: string | null;
}

export interface LLMCallRow {
  id: number;
  campaign_id: number;
  campaign_name: string;
  role: string;
  intent_id: number | null;
  run_id: number | null;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cache_read: number;
  cache_write: number;
  stop_reason: string | null;
  duration_ms: number | null;
  message_id: number | null;
  ts: number;
}

export interface LLMCallDetail extends LLMCallRow {
  message: RunMessage | null;
  run: Run | null;
}

export interface LogRow {
  id: number;
  campaign_id: number;
  campaign_name: string;
  intent_id: number | null;
  role: string;
  kind: string;
  summary: string;
  ts: number;
  has_detail: number;
}

export interface SettingsResp {
  values: Record<string, string | number>;
  overrides: Record<string, string>;
  anthropic_configured: boolean;
  fallbacks: boolean;
}

export interface PlatformInfo {
  platform: string;
  label: string;
  enabled: boolean;
  missing: string;
  doc: string;
  tools: { name: string; description: string; schema: Record<string, unknown> }[];
}

export interface AgentInfo {
  role: string;
  title: string;
  model: string;
  effort: string;
  max_turns: number;
  count?: number;
  description: string;
  system: string;
  tools: { name: string; description: string }[];
}

export interface SystemInfo {
  version: string;
  python: string;
  db_path: string;
  keys_dir: string;
  companies: number;
  tasks: number;
  users: number;
  webui: boolean;
}

export interface Badges {
  running: number;
  new_hot: number;
}
