// ---- 透传类型（与 09 state.py / 11-15 输出同形，snake_case 照写） ----
export interface Step { tool: string; args: Record<string, unknown> }
export interface ExecutedStep { tool: string; status: string; result: unknown }

// SSE 快照：stream_mode="values" 逐节点追加字段，故全可选
export interface AgentState {
  query?: string;
  correlation_id?: string;
  intent?: string;
  categories?: string[];
  plan?: Step[];
  steps?: ExecutedStep[];
  report?: string;
}

// 五种工具结果（ResultChart 按 result_type 分发后交给对应 *Option）
export interface BoxplotResult {
  gene: string;
  samples: Record<string, number[]>;
  summary: Record<string, { n: number; mean: number; median: number; sd: number | null }>;
  p_value: number | null;
}
export interface VolcanoResult {
  genes: { gene: string; logFC: number; p_value: number; adj_p_value: number }[];
}
export interface EnrichmentRow { id: string; term: string; p_value: number; adj_p_value: number; gene_count: number }
export interface BarplotResult { go: EnrichmentRow[]; kegg: EnrichmentRow[] }
export interface NetworkResult {
  nodes: { id: string; degree: number }[];
  edges: { source: string; target: string; score: number }[];
}
export interface KmCurveResult {
  km_curves: { group: string; time: number[]; survival: number[] }[];
  logrank_p: number;
  cox_hr: number;
  cox_p: number;
}

// /tools 响应（ToolDefinition 的透传；input_schema / frontend.result_type 是 wire key，不 camelCase 化）
export interface ToolMeta {
  name: string;
  description: string;
  category: string;
  runtime: string;
  input_schema: Record<string, unknown>;
  frontend: { result_type?: string };
}

// ---- 前端领域类型（camelCase；client.ts 把后端 snake_case → camelCase） ----
export interface Message { role: 'user' | 'assistant'; content: string }
export interface UploadResult { fileId: string; originalName: string; size: number }
export interface TaskSummary { id: string; userMessage: string; status: string; createdAt: number; updatedAt: number }
export interface TaskDetail extends TaskSummary {
  plan: Step[];
  steps: ExecutedStep[];
  report: string;
  error: string | null;
}
