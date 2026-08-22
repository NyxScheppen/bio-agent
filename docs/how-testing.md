# How: 测试规范

> 测试写法细节见 `CLAUDE.md` Part 4。本文档定义策略、层级和覆盖标准。

## 测试哲学

**验证管道正确性，不验证 LLM 文本质量。**
测试确保数据走对流程、结构正确、边界不崩。不测试"报告写得好不好"。

## 测试层级

| 层级 | 范围 | 优先 |
|------|------|------|
| **单元** | 纯函数（KM 估计、Cox 偏似然、PCA、富集统计、R 结果解析） | 最高——有纯逻辑就先测 |
| **集成** | 工具 `run()` / 编排管道（Mock LLM / Mock R 子进程） | 每个工具 ≥1 条 |
| **E2E** | 关键用户路径（发消息 → 走完四节点 → 收报告） | 每条用户故事 1 条 |

## Mock 原则

- 所有 LLM 调用处可注入 mock，返回预设 fixture
- R 工具测试 mock R 子进程（不真跑 Rscript）
- 外部 API（STRING / PubMed / Qdrant）monkeypatch 为 fake
- 测试不依赖真实 LLM、真实 R 环境、真实网络、真实文件系统

## 覆盖标准

- 每个工具 `run()` ≤ 5 个断言 | 纯函数测全 | 不追求百分比，追求"改了会不会炸"的信心

## 测试目录 & 清单

```
tests/{test_types,test_config,test_db,test_llm,test_tools,test_r_runner,
      test_rag,test_orchestration,test_api,test_single_gene,test_dge,
      test_enrichment,test_network,test_survival}/
```

每次编写测试后更新 `test-inventory.md`：新增了什么、检查方向、所属系统、在哪个功能阶段编写。
