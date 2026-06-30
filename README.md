# BioAI Agent

> 面向生物信息学与合成生物学领域的 AI 智能助手  
> 通过自然语言对话执行专业生信分析 —— 从数据上传到可视化全流程自动化

**版本**: 2.0 &nbsp;|&nbsp; **最后更新**: 2026-06-27

---

## 🔬 项目简介

BioAI Agent 是一个全栈 AI 应用，将大语言模型与生物信息学工具链深度整合。用户只需用自然语言描述需求（支持中文），系统即可自动完成文件识别、分析方案制定、R/Python 工具调用、结果报告生成的全流程。

适合生物信息学研究人员、合成生物学工程师，以及需要高效执行标准化生信分析的团队。

---

## ✨ 核心特性

- **Multi-Agent 架构** — Router → Planner → Executor → Reporter 流水线，全自动任务编排
- **54 个 Skill** — YAML 驱动的任务专精技能包，覆盖 16 个生信类别
- **45+ 专业工具** — 生存分析、差异表达、富集分析、机器学习、单细胞、空间转录组等
- **R 深度集成** — 子进程调用 Rscript，私有包库管理，无缝衔接 Bioconductor 生态
- **并行 + 竞速** — 依赖感知并行执行，Waterfall Racing 多工具竞速
- **护栏机制** — 空转检测、熔断器、自动恢复策略，防止失控
- **斜杠命令** — 19 个快捷命令（`/survival` `/deg` `/enrich` `/gsea` 等）
- **Session Memory** — 跨轮次会话记忆，支持短回复解析
- **自改进反馈** — 失败模式记录 → 分析 → 改进建议的闭环

---

## 📁 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | FastAPI 0.135+ (Python 3.10-3.12) |
| ASGI 服务器 | Uvicorn |
| AI / LLM | DeepSeek API（OpenAI 兼容接口） |
| 数据库 | SQLite + SQLAlchemy 2.0 |
| R 集成 | subprocess + Rscript (R 4.2+) |
| 前端 | Vite + React SPA |
| 数据处理 | Pandas, NumPy, Scikit-learn, SciPy |
| 可视化 | Matplotlib, Seaborn (Python) + ggplot2 (R) |

---

## 🚀 快速开始

### 环境要求

- **Python** 3.10 / 3.11 / 3.12
- **R** 4.2 或更高版本
- **操作系统** Windows 10/11（主平台），兼容 Linux

### 安装和启动

```batch
# 1. 检查环境
check_env.bat

# 2. 安装 R 依赖包（首次运行需要）
Rscript install_r_packages.R

# 3. 配置环境变量 —— 复制模板并填入你的 API Key
copy backend\.env_example backend\.env
# 编辑 backend\.env，将 DEEPSEEK_API_KEY 改为真实值

# 4. 启动应用
start_app.bat
```

应用将在 `http://127.0.0.1:8000` 启动，浏览器自动打开。

> ⚠️ `start_app.bat` 将自动创建虚拟环境、安装 Python 依赖、定位 Rscript，无需手动配置。

### 手动配置环境变量

如果不想使用启动脚本，手动创建 `backend/.env`：

```env
DEEPSEEK_API_KEY=sk-your-real-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-chat
API_HOST=127.0.0.1
API_PORT=8000
```

---

## 🏗 系统架构

```
用户输入
  → 命令解析 (19 个斜杠命令)
  → Router Agent: 任务分类
  → Skill Select: 匹配 54 个技能包
  → Planner Agent: 制定执行计划
  → [Delegator]: 复杂任务拆分子 Agent
  → Executor Agent: 并行/竞速工具调用 + 护栏保护
  → Reporter Agent: 生成结构化中文报告
  → 返回 { reply, files }
```

### 工具分类

| 类别 | 代表功能 |
|------|---------|
| 🔬 生存分析 | KM 曲线、Cox 回归、LASSO 预后模型 |
| 🧬 转录组 | DESeq2 / limma 差异表达、PCA |
| 🧪 富集分析 | GO / KEGG / GSEA / GSVA |
| 🤖 机器学习 | 随机森林、SVM、XGBoost、LASSO 特征选择 |
| 🕸 网络药理学 | PPI 网络、STRING 数据库分析 |
| 🔬 单细胞 | Seurat 标准流程 |
| 🗺 空间转录组 | 空间基因表达分析 |
| 🧲 虚拟扰动 | 基因 knock down / knock out 模拟 |
| 📚 文献检索 | PubMed 文献检索 |
| 🧬 单基因 | 表达分析、基因集相关性 |
| 📂 文件操作 | 多格式预览、GEO 数据下载 |
| 🔧 系统 | R/Python 环境诊断 |

---

## ⌨ 斜杠命令

| 命令 | 功能 | 命令 | 功能 |
|------|------|------|------|
| `/survival` | 单基因生存分析 | `/cox` | 批量 Cox 回归 |
| `/lasso` | LASSO-Cox 模型 | `/deg` | 差异表达 (limma) |
| `/deseq2` | DESeq2 差异分析 | `/pca` | PCA 分析 |
| `/enrich` | GO/KEGG 富集 | `/gsea` | GSEA 预排序 |
| `/ml` | ML 二分类 | `/compare` | 多模型比较 |
| `/ppi` | PPI 网络 | `/netpharm` | 网络药理学 |
| `/scrna` | 单细胞分析 | `/probe` | 文件探测 |
| `/geo` | GEO 下载 | `/lit` | 文献检索 |
| `/env` | 环境检测 | `/help` | 命令帮助 |

---

## 📂 项目结构

```
bio_test/
├── README.md
├── start_app.bat              # 一键启动
├── check_env.bat              # 环境检测
├── requirements.txt           # Python 依赖
├── install_r_packages.R       # R 包安装
├── .gitignore                 # Git 忽略规则
│
├── backend/
│   ├── .env_example           # 环境变量模板
│   ├── static/                # 前端 SPA（Vite build）
│   ├── storage/               # 上传和生成文件
│   ├── db_data/               # SQLite 数据库
│   └── app/
│       ├── main.py            # FastAPI 入口
│       ├── api/               # REST API（chat / upload / history / system）
│       ├── agent/             # Multi-Agent + Skill + Rules + Hooks
│       │   └── skills/packs/  # 18 个 YAML Skill 定义
│       ├── tools/             # 45+ 生信分析工具
│       ├── services/          # 业务服务层
│       ├── db/                # ORM + CRUD + 审计日志
│       ├── schemas/           # Pydantic 模型
│       ├── core/              # 配置与路径管理
│       └── utils/             # 工具函数
│
├── env/r_libs/                # R 私有包库
├── logs/                      # 日志目录
├── docs/                      # 开发文档
└── runtime/                   # 运行时脚本
```

---

## 🛠 开发指南

### 新增工具

```python
from app.agent.tool_registry import register_tool
from app.agent.tool_result import make_success_result

@register_tool(
    name="my_analysis",
    description="自定义分析",
    category="survival",
    timeout=1800,
    max_memory_mb=8192,
)
def my_analysis(file_path: str, gene: str, threshold: float = 0.05):
    try:
        # ... 执行分析 ...
        return make_success_result(
            message="分析完成",
            output_files=[...],
            summary={"up": 150, "down": 80}
        )
    except Exception as e:
        return make_error_result(message=f"失败: {e}", errors=[str(e)])
```

### 新增 Skill

在 `backend/app/agent/skills/packs/` 下创建 YAML 文件即可自动加载：

```yaml
skills:
  - skill_id: my_skill
    name: "自定义技能"
    category: transcriptome
    trigger_keywords_cn: [自定义, 特殊分析]
    allowed_tools: [run_bulk_rnaseq_deg_analysis]
    max_tool_rounds: 12
    implementation_status: implemented
```

### 运行测试

```bash
# 工具返回协议测试
.venv/Scripts/python.exe backend/tests/test_tool_result.py

# 工具生命周期测试
.venv/Scripts/python.exe backend/tests/test_tool_lifecycle.py

# Skill 系统测试
.venv/Scripts/python.exe backend/tests/test_skill_system.py

# 全量回归测试
.venv/Scripts/python.exe backend/tests/test_integration.py
```

---

## 📄 License

待定

---

🤖 Generated with Claude Code
