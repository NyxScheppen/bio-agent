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
- [ ] `useSSE`：POST `/chat`（fetch + `ReadableStream` 读流）、逐条解析 `data: {json}` SSE 帧、把每帧完整状态快照回调出去；非 200 / 流中断 → 错误态
- [ ] 三个 Zustand store：`chatStore`（消息 + 当前状态快照 + 报告）、`taskStore`（任务列表 + 当前任务）、`uploadStore`（上传中 + file_id）
- [ ] 五个结果图组件（boxplot/volcano/barplot/network/km_curve）各自 `*Option(data)` 是纯函数，返回确定性的 ECharts option 对象
- [ ] 组件渲染：聊天面板（消息气泡 + 输入框）、步骤列表（线性步骤 + 状态）、结果图（按 `result_type` 分发）、任务历史（表格 + 点击回看）、文件上传（选文件 → 拿 file_id）
- [ ] `frontend.result_type` 五种值都有对应图表；未知 `result_type` → 不崩，展示原始 JSON

## 技术方案

- **栈**：React 18 + Vite + TypeScript（`strict: true`）+ Zustand + ECharts + Tailwind CSS；测试 Vitest + `@testing-library/react` + `@testing-library/jest-dom`。前端是独立包，质量门不走 Python 的 ruff/pyright/pytest，走 eslint + tsc + vitest。
- **ECharts 用法**：`import * as echarts from 'echarts'`（全量引入，MVP 不 tree-shaking，本地作品集体积可接受）；一个薄 `ECharts` 组件（`useRef` + `useEffect` 挂 `echarts.init`，`option` 变化时 `setOption`），不引 `echarts-for-react`。选项构建收敛到 `charts/options.ts` 纯函数，单测不碰 DOM。
- **SSE 是 POST**：`/chat` 是 POST（EventSource 只支持 GET），故用 `fetch` + `response.body.getReader()` 手写流解析。每帧是 `data: {完整状态快照}\n\n`（10-api `stream_mode="values"`），前端把最新快照写进 `chatStore.currentState`：`plan` 出现=规划完成、`steps` 追加=执行进度、`report` 出现=结束。
- **步骤显示是线性的**：plan-and-execute 产出线性步骤（不是真 DAG），StepList 是垂直列表不是图。早期「步骤 DAG」的说法在此收敛为「线性步骤列表」。每步展示工具名 + 状态（pending/running/done/failed）。
- **result_type → 图表** 映射表：

| result_type | 数据来源 | ECharts series |
|---|---|---|
| `boxplot` | single_gene_expression（samples/summary） | boxplot |
| `volcano` | limma_dge（genes: logFC/p_value） | scatter（-log10(p) vs logFC，按显著性着色） |
| `barplot` | go_kegg（go/kegg: term/p_value） | bar（-log10(p) 横向条形） |
| `network` | ppi_network（nodes/edges） | graph（force 力导向布局） |
| `km_curve` | km_cox（km_curves: time/survival） | line（`step: 'end'` 阶梯） |

### 目录结构

```
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  tailwind.config.js
  index.html
  src/
    main.tsx
    App.tsx
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

### `hooks/useSSE.ts`（核心签名，完整实现见 plan）

```ts
// 返回 { run, stop, error }；run(url, body) 发 POST 并把每帧 JSON 交给 onEvent
export function useSSE(onEvent: (snapshot: AgentState) => void): {
  run: (url: string, body: unknown) => Promise<void>;
  stop: () => void;
  error: string | null;
};
```

### `charts/options.ts`（纯函数签名）

```ts
export function boxplotOption(data: any): echarts.EChartsOption;
export function volcanoOption(data: any): echarts.EChartsOption;
export function barplotOption(data: any): echarts.EChartsOption;
export function networkOption(data: any): echarts.EChartsOption;
export function kmCurveOption(data: any): echarts.EChartsOption;
```

### `stores/chatStore.ts`（Zustand，签名）

```ts
interface ChatState {
  messages: Message[];                 // 用户/助手消息
  currentState: AgentState | null;     // 最新 SSE 快照
  status: 'idle' | 'streaming' | 'done' | 'error';
  send: (message: string) => Promise<void>;  // 调 useSSE 的 run，逐帧更新 currentState
}
```

## 测试要点

- [ ] `tests/frontend/`（Vitest + RTL）：
  - [ ] `options.ts` 纯函数：五种 `*Option` 各返回确定性 option（同输入同输出、含期望的 series.type、无 `undefined` 关键字段）；`volcanoOption` 对空 genes 返回空 series 不抛
  - [ ] `useSSE`：mock `fetch` 返回含多帧 `data: {...}\n\n` 的流 → `onEvent` 按帧逐次收到 JSON；非 200 抛/置 error；`stop()` 中止 reader
  - [ ] `chatStore`：`send` 把用户消息入 messages、`currentState` 随帧更新、末帧含 report 后 status='done'
  - [ ] `ResultChart` 分发：`result_type="volcano"` 渲染 scatter；未知类型渲染 JSON 而非崩
  - [ ] `FileUpload`：mock `client.upload` → 成功后写 `uploadStore.fileId`
- [ ] 集成测试：无（不真起后端；所有端点经 `client.ts` 层 mock）
- [ ] E2E 测试：无（Playwright 不在 MVP）

## 完成定义

- [ ] `npm run lint` 零报错、`npm run typecheck` 零报错、`npm run test` 全绿
- [ ] `test-inventory.md` 已更新（前端测试条目：图表选项纯函数 / useSSE / stores / 组件分发）
- [ ] 手动验证：`npm run dev` + 后端起起来，聊天框发一句「帮我做 DGE」，能出步骤列表 + 火山图 + 任务历史可回看

## 跨 spec 对齐点（实现时核对，非本 spec 决定）

- **steps 状态字段**：StepList 要显示 pending/running/done/failed，依赖 09-orchestration 的 `steps` 元素里是否带 `status`。若 09 未定义 status 字段，本 spec 需与 09 对齐补上（见下方待确认清单）。
- **report 内容形态**：reporter（09）产出的 `report` 是纯文本还是带结构化结果引用？决定 ResultChart 是「从 `steps` 里取 tool 结果」还是「从 `report` 里取」。默认：结果图数据取 `steps` 中每个工具的 `result`，`report` 只做文字总结。
