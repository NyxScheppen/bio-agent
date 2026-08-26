# 前端（React + Vite + TypeScript + ECharts + Tailwind）

> 范围：`frontend/`（独立 npm 包）。聊天面板 + 步骤列表 + 结果图（ECharts）+ 任务历史 + 文件上传。
> 消费 10-api 的 5 个端点；SSE 用自定义 `useSSE` hook（POST + fetch 流，非 EventSource）。
> 纯前端 spec：不含编排、不含后端逻辑；图表选项构建是纯函数，可单测。
> 图表库 **ECharts**、样式 **Tailwind CSS**（本次已确认）。

## 元信息

- **前置依赖**：10-api（5 端点契约）、11-15（`frontend.result_type` 五种取值）
- **无循环依赖**：本 spec 只 import 第三方（react/zustand/echarts/tailwind），不 import 任何 `bioagent`

## 用户故事

> 作为用户，我想要「聊天框里丢一句话 + 上传数据文件，就看到 agent 依次跑哪些步骤、每步的结果图，并能在历史里点回任意一次任务」，以便像用聊天助手一样完成一次转录组分析。

## 验收标准

- [ ] `npm run dev` 起 Vite；`npm run lint`（eslint）、`npm run typecheck`（`tsc --noEmit`）、`npm run test`（vitest）全绿
- [ ] `useSSE`：POST `/chat`（fetch + `ReadableStream` 读流）、逐条解析 `data: {json}` SSE 帧；有 `done` 键 → resolve、有 `error` 键 → 置 error、否则把整帧快照回调 `onEvent`；非 200 / 流中断 → 错误态
- [ ] 三个 Zustand store：`chatStore`（消息 + 当前状态快照 + 报告）、`taskStore`（任务列表 + 当前任务）、`uploadStore`（上传中 + fileId）
- [ ] 五个结果图组件（boxplot/volcano/barplot/network/km_curve）各自 `*Option(data)` 是纯函数，返回确定性的 ECharts option 对象
- [ ] 组件渲染：聊天面板（消息气泡 + 输入框）、步骤列表（线性步骤 + 状态）、结果图（按 `result_type` 分发）、任务历史（表格 + 点击回看，失败任务显示 `error`）、文件上传（选文件 → 拿 file_id）
- [ ] `frontend.result_type` 五种值都有对应图表；未知 `result_type` → 不崩，展示原始 JSON

## 技术方案

- **栈**：React 19 + Vite + TypeScript 5.9（`strict: true`）+ Zustand + ECharts + Tailwind CSS v4（CSS-first，`@tailwindcss/vite` 插件，无 `tailwind.config.js`）；测试 Vitest + `@testing-library/react` + `@testing-library/jest-dom`。前端是独立包，质量门不走 Python 的 ruff/pyright/pytest，走 eslint + tsc + vitest。
- **版本注**：TypeScript 锁 `^5.9.3` —— TS 7.0 是原生编译器，`typescript-eslint@8` 的 peer 要求 `<6.1.0`，二者不兼容，故回退到 5.x。
- **ECharts 用法**：`import * as echarts from 'echarts'`（全量引入，MVP 不 tree-shaking，本地作品集体积可接受）；一个薄 `ECharts` 组件（`useRef` + `useEffect` 挂 `echarts.init`，`option` 变化时 `setOption`），不引 `echarts-for-react`。选项构建收敛到 `charts/options.ts` 纯函数，单测不碰 DOM。
- **SSE 是 POST**：`/chat` 是 POST（EventSource 只支持 GET），故用 `fetch` + `response.body.getReader()` 手写流解析。每帧是 `data: {完整状态快照}\n\n`（10-api `stream_mode="values"`），前端把最新快照写进 `chatStore.currentState`：`plan` 出现=规划完成、`steps` 追加=执行进度、`report` 出现=结束。
- **步骤显示是线性的**：plan-and-execute 产出线性步骤（不是真 DAG），StepList 是垂直列表不是图。早期「步骤 DAG」的说法在此收敛为「线性步骤列表」。状态来源（09 已定）：`steps` 元素带 `status`（executor 写 `"completed"`），pending = `plan` 中不在 `steps` 里的步骤，failed = 任务级（task `status=="failed"`），无逐步 running（executor 一次性跑完所有步骤）。
- **result_type → 图表** 映射表：

| result_type | 数据来源 | ECharts series |
|---|---|---|
| `boxplot` | single_gene_expression（samples/summary） | boxplot |
| `volcano` | limma_dge（genes: logFC/p_value） | scatter（-log10(p) vs logFC，按显著性着色） |
| `barplot` | go_kegg（go/kegg: term/p_value） | bar（-log10(p) 横向条形） |
| `network` | ppi_network（nodes/edges） | graph（force 力导向布局） |
| `km_curve` | km_cox（km_curves: time/survival） | line（`step: 'end'` 阶梯） |

**`result_type` 来源**：`result_type` 不随 SSE 快照下发。前端启动时 `listTools()`（`GET /tools`）建 `tool_name → frontend.result_type` 映射；`ResultChart` 拿 `step.tool` 查映射得 `result_type`，再按上表分发。这是 `listTools` 的唯一消费方，也避免 09 在 step 里重复塞 `result_type`（第二份真相）。

### 目录结构

```
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    index.css              # @import "tailwindcss";（v4 CSS-first）
    main.tsx
    App.tsx
    types.ts              # 共享 TS 类型（见下方「类型定义」）
    api/client.ts          # fetch 封装：chatSSE/listTasks/getTask/upload/listTools
    hooks/useSSE.ts        # POST /chat 流式 hook
    stores/chatStore.ts
    stores/taskStore.ts
    stores/uploadStore.ts
    charts/options.ts      # 纯函数：boxplotOption/volcanoOption/barplotOption/networkOption/kmCurveOption
    charts/ECharts.tsx     # 薄 echarts 挂载组件
    components/ChatPanel.tsx
    components/StepList.tsx
    components/ResultChart.tsx   # result_type → option 分发
    components/TaskHistory.tsx
    components/FileUpload.tsx
```

### 类型定义（`src/types.ts`）

> 分两类：**透传类型**（后端 wire shape，snake_case 照写，前端不转换）与**前端领域类型**（camelCase，`client.ts` 统一转换）。

```ts
// ---- 透传类型（与 09 state.py / 11-15 输出同形，snake_case 照写） ----
interface Step { tool: string; args: Record<string, unknown> }
interface ExecutedStep { tool: string; status: string; result: unknown }

// SSE 快照：stream_mode="values" 逐节点追加字段，故全可选
interface AgentState {
  query?: string;
  correlation_id?: string;
  intent?: string;
  categories?: string[];
  plan?: Step[];
  steps?: ExecutedStep[];
  report?: string;
}

// 五种工具结果（ResultChart 按 result_type 分发后交给对应 *Option）
interface BoxplotResult {
  gene: string;
  samples: Record<string, number[]>;
  summary: Record<string, { n: number; mean: number; median: number; sd: number | null }>;
  p_value: number | null;
}
interface VolcanoResult {
  genes: { gene: string; logFC: number; p_value: number; adj_p_value: number }[];
}
interface EnrichmentRow { id: string; term: string; p_value: number; adj_p_value: number; gene_count: number }
interface BarplotResult { go: EnrichmentRow[]; kegg: EnrichmentRow[] }
interface NetworkResult {
  nodes: { id: string; degree: number }[];
  edges: { source: string; target: string; score: number }[];
}
interface KmCurveResult {
  km_curves: { group: string; time: number[]; survival: number[] }[];
  logrank_p: number;
  cox_hr: number;
  cox_p: number;
}

// /tools 响应（ToolDefinition 的透传；input_schema / frontend.result_type 是 wire key，不 camelCase 化）
interface ToolMeta {
  name: string;
  description: string;
  category: string;
  runtime: string;
  input_schema: Record<string, unknown>;
  frontend: { result_type?: string };
}

// ---- 前端领域类型（camelCase；client.ts 把后端 snake_case → camelCase） ----
interface Message { role: 'user' | 'assistant'; content: string }
interface UploadResult { fileId: string; originalName: string; size: number }
interface TaskSummary { id: string; userMessage: string; status: string; createdAt: number; updatedAt: number }
interface TaskDetail extends TaskSummary {
  plan: Step[];
  steps: ExecutedStep[];
  report: string;
  error: string | null;
}
```

### 端点与 `api/client.ts`（5 端点）

| 方法 | 路径 | client 函数 | 返回 |
|---|---|---|---|
| POST | `/chat` | `chatSSE`（经 `useSSE`） | SSE 流（`AgentState` 快照帧） |
| GET | `/tasks` | `listTasks` | `TaskSummary[]` |
| GET | `/tasks/{task_id}` | `getTask` | `TaskDetail` |
| POST | `/uploads` | `upload` | `UploadResult` |
| GET | `/tools` | `listTools` | `ToolMeta[]` |

`client.ts` 是 snake_case → camelCase 的唯一转换点（`file_id`→`fileId`、`original_name`→`originalName`、`user_message`→`userMessage`、`created_at`→`createdAt`、`updated_at`→`updatedAt`）；SSE 快照与工具结果属透传，不转换。

### `hooks/useSSE.ts`

```ts
// 返回 { run, stop, error }。run() 发 POST，用 fetch + response.body.getReader() 逐行读流，
// 按 "\n\n" 切帧、每帧去掉 "data: " 前缀后 JSON.parse，再按帧内容分派：
//   - 帧含 "done" 键   → resolve（正常结束）
//   - 帧含 "error" 键  → 置 error 并 reject
//   - 否则             → 整帧是完整状态快照，onEvent(snapshot)
// 非 200（!resp.ok）→ 置 error；stop() 调 reader.cancel() 中止读取。
export function useSSE(onEvent: (snapshot: AgentState) => void): {
  run: (url: string, body: unknown) => Promise<void>;
  stop: () => void;
  error: string | null;
};
```

### `charts/options.ts`（纯函数签名）

```ts
export function boxplotOption(data: BoxplotResult): echarts.EChartsOption;
export function volcanoOption(data: VolcanoResult): echarts.EChartsOption;
export function barplotOption(data: BarplotResult): echarts.EChartsOption;
export function networkOption(data: NetworkResult): echarts.EChartsOption;
export function kmCurveOption(data: KmCurveResult): echarts.EChartsOption;
```

### `stores/chatStore.ts`（Zustand，签名）

```ts
interface ChatState {
  messages: Message[];                 // 用户/助手消息
  currentState: AgentState | null;     // 最新 SSE 快照
  status: 'idle' | 'streaming' | 'done' | 'error';
  send: (message: string) => Promise<void>;  // POST /chat，复用 useSSE 的 readSSE 核心（store action 不能调 hook），逐帧更新 currentState
}
```

## 测试要点

- [ ] 测试（Vitest + RTL，colocated 为 `src/**/*.test.ts(x)`）：
  - [ ] `options.ts` 纯函数：五种 `*Option` 各返回确定性 option（同输入同输出、含期望的 series.type、无 `undefined` 关键字段）；`volcanoOption` 对空 genes 返回空 series 不抛
  - [ ] `useSSE`：mock `fetch` 返回含多帧 `data: {...}\n\n` 的流 → `onEvent` 按帧逐次收到 JSON；非 200 抛/置 error；`stop()` 中止 reader
  - [ ] `chatStore`：`send` 把用户消息入 messages、`currentState` 随帧更新、末帧含 report 后 status='done'
  - [ ] `ResultChart` 分发：给定 `tool→result_type` 映射（`limma_dge`→`volcano`）+ 一个 `step`（`tool="limma_dge"`）→ 渲染 scatter；未知 result_type → 渲染 JSON 而非崩
  - [ ] `FileUpload`：mock `client.upload` → 成功后写 `uploadStore.fileId`
- [ ] 集成测试：无（不真起后端；所有端点经 `client.ts` 层 mock）
- [ ] E2E 测试：无（Playwright 不在 MVP）

## 完成定义

- [ ] `npm run lint` 零报错、`npm run typecheck` 零报错、`npm run test` 全绿
- [ ] `test-inventory.md` 已更新（前端测试条目：图表选项纯函数 / useSSE / stores / 组件分发）
- [ ] 手动验证：`npm run dev` + 后端起起来，聊天框发一句「帮我做 DGE」，能出步骤列表 + 火山图 + 任务历史可回看

## 已锁定的跨 spec 决策（09/10 已同步）

- **steps 带 status**（已定）：09 的 `steps` 元素带 `status`（executor 写 `"completed"`）。StepList：`plan` 中不在 `steps` 里的 = pending，`steps` 里的 = done；failed 是任务级（`status=="failed"`）。
- **report 纯文本 + 图取 steps**（已定）：reporter 产出 `report` 是 markdown 纯文本；ResultChart 从 `steps` 里每个工具的 `result` 取数据画图（按 `result_type` 分发），`report` 只做文字总结。
- **失败原因可回看**（已定）：task 表有 `error` 列（`str | None`），`GET /tasks/{id}` 的 `TaskDetail` 带 `error`；TaskHistory 点开失败任务时展示 `error` 文本。
