# -*- coding: utf-8 -*-
"""Generate the two judge-prep DOCX deliverables.

Outputs:
  docs/iGEM-Judge-QA-print.docx   - full bilingual spoken-answer print version
  docs/iGEM-Judge-English-cheatsheet.docx - 15 English on-stage answers only
"""

from docx import Document
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn


def set_font(run, size=None, bold=None, color=None):
    run.font.name = "Calibri"
    r = run._element.rPr.rFonts
    r.set(qn("w:eastAsia"), "Microsoft YaHei")
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = RGBColor(*color)


def para(doc, text, style=None, size=10.5, bold=False, color=None):
    p = doc.add_paragraph()
    if style:
        p.style = style
    run = p.add_run(text)
    set_font(run, size=size, bold=bold, color=color)
    return p


def add_question(doc, q, variants, zh, en):
    para(doc, q, style="Heading 2")
    para(doc, variants, size=9.5, bold=True, color=(0x59, 0x66, 0x80))
    para(doc, "现场版（中文）", size=10, bold=True)
    para(doc, zh)
    para(doc, "On stage (English)", size=10, bold=True)
    para(doc, en)


QUESTIONS = [
    (
        "Q1. 你的软件是什么？给谁用、解决什么问题？",
        '问法：① "What does your software do?" ② "Who is it for?" ③ 一句话概括。',
        "BioAI Agent 是我们开源的一个本地优先的生信分析工作站：研究者把组学数据留在自己电脑上，"
        "用自然语言说出想做的分析，系统自动规划并调用内置的 40 个分析工具，回传可下载的结果文件、"
        "图表和方法总结。我们的定位很克制——它不是替代生信专家的判断，而是消除'有了科学假设'到"
        "'完成第一次可复现计算'之间的操作门槛。",
        "BioAI Agent is a local-first bioinformatics workstation: upload local omics data, describe the "
        "analysis in plain language, and the system plans and runs one of its 40 built-in tools, returning "
        "downloadable results, figures and a methods summary. Our principle is explicit \u2014 it never "
        "replaces a bioinformatician's judgment; it removes the friction between 'I have a hypothesis' and "
        "'I have a first reproducible result'.",
    ),
    (
        "Q2. 你的软件和主项目 DENTAL SHIELD 是什么关系？",
        '问法：① "How does the software serve your project?" ② "Why did an oral-health project need a '
        'bioinformatics tool?" ③ "它是你们自己用的，还是独立通用工具？"',
        "DENTAL SHIELD 的干实验——靶点筛选、公开组学数据重分析、文献整合——需要把生物问题变成可复现"
        "的计算证据。团队在人类实践里反复听到同一个痛点：生信门槛高、文本对话不可靠，于是我们把"
        "负责任研究与创新的方法直接映射成这套软件的功能边界。所以它先服务我们自己的项目，同时因为"
        "声明式技能白名单的设计，任何研究者都能拿它做标准化分析。",
        "DENTAL SHIELD's dry lab \u2014 target screening, public-data reanalysis, literature mining \u2014 "
        "needed a reproducible way to turn biological questions into computational evidence. Our Human "
        "Practices kept surfacing the same pain, so we mapped responsible-research thinking directly onto "
        "the software's boundaries. It serves our project first \u2014 and because execution goes through a "
        "declarative tool allowlist, it works for any researcher.",
    ),
    (
        "Q3. 大模型会瞎编，你怎么保证分析结果科学正确？",
        '问法：① "How do you validate biological correctness?" ② "LLMs hallucinate \u2014 how do you stop '
        'it?" ③ "你的测试是测流程还是测数值？"',
        "我们从结构上防幻觉：大模型只负责规划和路由，从不生成可运行的分析代码，真正执行的是 40 个"
        "预注册的确定性工具。正确性分三层：流程有自动化测试，确定性计算有基准数值校验，R 分析在合成"
        "数据和已知数据集上真实跑过并留有执行记录。而且每次运行都带参数、耗时和审计——流畅的文字"
        "不算证据，产出的文件和日志才算。在冻结之后的更新里，我们又补了数值基准测试，让'数值正确'"
        "也有自动化断言。",
        "We fight hallucination structurally: the model only plans and routes \u2014 it never emits runnable "
        "analysis code; 40 pre-registered deterministic tools do the actual computation. Correctness has "
        "three layers: automated pipeline tests, benchmark values for deterministic math, and real R runs "
        "on synthetic and known datasets, all logged. Every run carries its parameters, timing and audit "
        "trail \u2014 a fluent sentence is never evidence; produced files and logs are. In our post-freeze "
        "updates we also added numerical benchmark tests, so 'the numbers are right' is itself an automated "
        "claim.",
    ),
    (
        "Q4. 超时和资源限制是真的能停吗？护栏实不实？",
        '问法：① "What happens when a tool runs too long?" ② "How do your guardrails actually work?"',
        "是真的停。每个工具都在独立子进程里运行，超时或取消时强杀整个进程树，不是只停止等待，还有"
        "回归测试证明不会留下孤儿进程。冻结之后我们又做了一项更新：对工具进程做内存和 CPU 的实时"
        "采样，资源占用现在是实测值而不是估算。再加上技能白名单、轮次上限和自动恢复，这套护栏是"
        "实际生效、有测试背书的。",
        "Real termination. Every tool runs in a separate process; on timeout or cancel we hard-kill the "
        "entire process tree \u2014 not just stop waiting \u2014 and a regression test proves no orphan "
        "survives. After the freeze we added real-time memory and CPU sampling of the tool process, so "
        "resource numbers are measured, not estimated. Together with Skill allowlists, round limits and "
        "auto-recovery, these guardrails actually run and are tested.",
    ),
    (
        "Q5. 和直接问 ChatGPT、用 Galaxy 有什么不同？护城河是什么？",
        '问法：① "Why not just ask ChatGPT to write the R code?" ② "What\u2019s different from Galaxy?" '
        '③ "你的独特贡献是什么？"',
        "通用大模型做生信有五个具体障碍：不会命令行、流程步骤易错、对话记录不能当证据、模型可能"
        "伪造路径和图、数据上云有合规风险。我们逐一对应：自然语言加图形界面；54 个固化标准流程的"
        "技能；真实产物加审计；只执行白名单内的工具；数据全程留在本机。Galaxy 有流程但没有智能"
        "编排，通用对话有智能但没有可验证的执行——我们要的是两者的结合。",
        "General LLMs have five concrete barriers in bioinformatics: no command-line skills, error-prone "
        "workflow ordering, chat logs aren't evidence, fabricated paths and figures, and data-compliance "
        "risk in the cloud. We answer each: natural language plus GUI; 54 Skills that freeze correct "
        "workflows; real artifacts plus audit; execution only through a whitelist; and data that never "
        "leaves the machine. Galaxy has pipelines but no agent; chat has an agent but no verified "
        "execution \u2014 we combine both.",
    ),
    (
        "Q6. 数据存哪、谁能访问？隐私和 Responsible AI 怎么做？",
        '问法：① "Where is the data stored and who can access it?" ② "How do you handle sensitive omics '
        'data?" ③ "Your Responsible AI statement?"',
        "默认是单机单用户，服务只绑定本机地址，数据和结果留在本地目录和本地数据库，删除会话会连带"
        "清理文件和记录。会话标识是加密随机生成、不可猜的；跨域访问用白名单；危险的网页类文件强制"
        "下载而不是在线渲染。我们的诚实边界是：超出本机的部署需要补认证和加密，这些写得很清楚。"
        "模型输出要求人工复核，外部数据库失败也绝不会记成分析成功。在冻结之后的更新里，我们还收紧"
        "了跨域白名单并去掉了共享的默认会话，进一步堵住了串号和越界访问的口子。",
        "By default it's single-user, bound to localhost; data and results stay in local storage and a "
        "local database, and deleting a session removes its files and records. Session IDs are "
        "cryptographically random, cross-origin access is allowlisted, and dangerous inline files are "
        "forced to download. Our honest boundary: deploying beyond localhost needs auth and encryption "
        "\u2014 stated clearly. Model outputs require human review, and external-database failures are never "
        "reported as successful analyses. In our post-freeze updates we tightened the cross-origin "
        "allowlist and removed the shared default session, closing data-mixing and cross-access gaps.",
    ),
    (
        "Q7. 怎么证明工程是成功的？测试证据在哪？",
        '问法：① "Walk me through your engineering success." ② "What\u2019s tested, and does it pass?" '
        '③ "Give me your DBTL evidence."',
        "三件事。第一，自动化测试全绿——冻结前最近一次公开验证记录是 220 项，冻结之后我们继续更新"
        "并实测，现在是 230 项。第二，关键分析不是模拟而是真实执行：生存分析、差异表达、富集、机器"
        "学习、网络药理、单细胞、空间转录组都真实跑出过结果文件，逐项有验证记录。第三，可复现性用"
        "三重锁定：Python、前端、R 的依赖都有锁文件，外加持续集成。",
        "Three things. First, the automated suite is green \u2014 220 tests at the last public pre-freeze "
        "verification, and 230 after our post-freeze updates. Second, the key analyses ran for real, not "
        "mocked \u2014 survival, differential expression, enrichment, machine learning, network "
        "pharmacology, single-cell, spatial \u2014 each with recorded output files. Third, reproducibility "
        "is triple-locked: Python, frontend and R dependencies are all pinned, plus continuous "
        "integration.",
    ),
    (
        "Q8. 别人怎么跑起来？可复现吗？",
        '问法：① "How do I install and run it?" ② "Can someone else reproduce your demo?"',
        "Windows 上三步：跑环境检测脚本；首次运行时装一次 R 依赖；然后一键启动——启动器自动创建虚拟"
        "环境、安装 Python 依赖、定位 R 环境并打开界面。依赖全部锁定，有持续集成，前端源码和构建"
        "产物都在仓库里，新克隆下来就能复现。",
        "Three steps on Windows: run the environment check, install R dependencies once on first run, then "
        "one-click launch \u2014 the launcher creates the virtual environment, installs Python dependencies, "
        "locates R and opens the app. Dependencies are pinned, CI is configured, and both frontend source "
        "and build output are in the repo \u2014 a fresh clone reproduces it.",
    ),
    (
        "Q9. 为什么选这个架构？最大的权衡是什么？",
        '问法：① "Why this architecture?" ② "Key design trade-offs?" ③ "Why local-first, and why not a '
        'pure LLM agent?"',
        "最大的权衡是我们主动放弃'让大模型随便写代码'，换来确定性、可审计、能强杀。所以架构是五层："
        "路由、技能规则、规划、执行、报告，每一步都被声明式白名单约束。我们用 SCQAB 框架把需求推演"
        "了一遍：背景是工具散落在 R、Python 和数据库；冲突是对话不能证明计算；问题是怎样降门槛又不"
        "丢合规、可复现和本地安全；答案是本地优先加沙箱化声明式执行；构建就是 40 个工具、54 个技能"
        "和整套测试。另外我们选 Windows 优先，因为那是湿实验室的主流环境。",
        "The core trade-off was giving up 'let the model write arbitrary code' to gain determinism, "
        "auditability and a kill switch. Hence five layers \u2014 routing, Skill rules, planning, execution, "
        "reporting \u2014 every step constrained by a declarative allowlist. We reasoned through SCQAB: "
        "tools scattered across R, Python and databases; chat can't prove computation; how to lower the "
        "barrier while keeping compliance, reproducibility and local security; the answer \u2014 local-first "
        "with sandboxed declarative execution; the build \u2014 40 tools, 54 Skills and a full test suite. "
        "We also chose Windows-first because that's the wet lab's dominant environment.",
    ),
    (
        "Q10. \u201c并行 + 竞速 + 自动恢复\u201d这些特性是真的在跑吗？",
        '问法：① "Is your parallel-and-racing claim real?" ② "Some READMEs overstate features \u2014 what '
        'actually runs?"',
        "敢这么说：我们写进文档的能力，都有测试或真实执行记录。并行执行按依赖分批是真实接线并测试"
        "的；差异表达竞速真的同时跑连续表达和计数两条工具链、取先成功者；失败恢复会自动处理格式、"
        "编码、缺列这几类问题。仍属实验性的东西我们如实标注，绝不夸大。",
        "Our rule is: if we claim it, a test or a real run backs it. Dependency-aware parallel batches are "
        "wired and tested; the DEG race genuinely runs the continuous and count pipelines side by side and "
        "returns the first success; recovery auto-handles format, encoding and missing-column failures. "
        "Anything still experimental is honestly labeled \u2014 we never oversell.",
    ),
    (
        "Q11. 谁真的用过？可访问性怎么样？",
        '问法：① "Has a real non-expert used this?" ② "Any adoption beyond your team?"',
        "首先是我们的跨学科团队在用——临床、材料、计算背景的成员都在 DENTAL SHIELD 里实际使用它。"
        "现在它是开源的，文档、持续集成、一键启动都齐备，面向所有需要标准化生信流程的研究者。如果"
        "您追问第三方采用情况，我诚实回答：让更多真实用户用起来，正是我们赛后的首要目标。",
        "Our interdisciplinary team \u2014 clinical, materials, computational backgrounds \u2014 used it "
        "throughout DENTAL SHIELD. It's now open source with documentation, CI and a one-click launcher, "
        "aimed at any researcher needing standardized bioinformatics. If you push on third-party adoption, "
        "I'll be honest: growing real users is our first post-competition goal.",
    ),
    (
        "Q12. 安全与生物安全怎么保障？",
        '问法：① "How does the software support your project\u2019s safety?" ② "Any data-risk or dual-use '
        'concerns?"',
        "两面看。生物学上，DENTAL SHIELD 有双重安全模块——营养缺陷自毁和本底信号屏蔽，加上伦理评审"
        "和定量伦理风险模型。软件这边不产生任何生物体，主要风险是数据隐私，本地优先的设计就是为此。"
        "输入侧我们还防了恶意文件、路径穿越和服务器端请求伪造这类攻击。",
        "Two angles. Biologically, DENTAL SHIELD has dual safety modules \u2014 auxotrophy self-destruct and "
        "background-signal silencing \u2014 plus ethics review and a quantitative risk model. The software "
        "creates no organism; its main risk is data privacy, which local-first design addresses. On the "
        "input side we also guard against malicious files, path traversal and server-side request forgery.",
    ),
    (
        "Q13. 谁做了什么？归因清楚吗？",
        '问法：① "Who built this, and who did what?" ② "Any attribution you want to highlight?"',
        "我们是兰州大学的 LZU-GANSU 队，34 名成员横跨口腔、临床、公卫、生科和材料等专业，由两位主要"
        "指导老师带领。软件维护在 iGEM 官方软件仓库，完整开发历史在公开镜像上可查；个人署名与官网"
        "归因表一致。",
        "We are team LZU-GANSU from Lanzhou University \u2014 34 members across dentistry, clinical "
        "medicine, public health, life sciences and materials, led by two principal investigators. The "
        "software lives in the official iGEM software repository with a public development mirror; "
        "individual credits match our Attributions Form.",
    ),
    (
        "Q14. 下一步计划？长期影响？",
        '问法：① "What\u2019s next for the software?" ② "How will it make a wider impact?"',
        "短期是把规划中的能力补齐——单细胞注释、拟时序、空间反卷积、分子对接，并做出教程。长期是把 "
        "BioAI Agent 做成可复现生信分析的开放基座，降低门槛，尤其是帮助资源有限的团队——这和 "
        "DENTAL SHIELD 关注医疗资源匮乏人群的初心一致。现阶段我们以影响力和采用率为目标，不是营收。",
        "Short term: complete the planned capabilities \u2014 single-cell annotation, trajectory, spatial "
        "deconvolution, docking \u2014 and produce tutorials. Long term: make BioAI Agent an open foundation "
        "for reproducible bioinformatics, especially for under-resourced teams, mirroring DENTAL SHIELD's "
        "own focus on people with scarce access to care. Our metric now is impact and adoption, not "
        "revenue.",
    ),
    (
        "Q15. （压力题）\u201c这不就是个调用大模型的壳吗？\u201d",
        '问法：① "Isn\u2019t this just a wrapper around an LLM?" ② "A bioinformatician could just run R '
        '\u2014 why your tool?"',
        "公平的质疑。如果大模型直接写 R 代码，那确实只是个壳——这正是我们拒绝的架构。这里模型只规划"
        "和路由，执行的是 40 个版本受控的确定性工具，跑在可强杀、可审计的沙箱里。而且目标用户不是"
        "已经会跑 R 的生信专家，而是被环境配置、格式检查、依赖冲突和复现记录拖住的生物学家。我们"
        "消掉的是重复劳动，从不替代专家判断。",
        "Fair challenge. If the model wrote R code, it would just be a shell \u2014 that's exactly the "
        "architecture we rejected. Here the model only plans and routes; 40 version-controlled "
        "deterministic tools execute inside a killable, auditable sandbox. And the target user isn't the "
        "bioinformatician who already runs R \u2014 it's the biologist bottlenecked by setup, formats, "
        "dependencies and bookkeeping. We remove friction, never expert judgment.",
    ),
]

CLOSER_ZH = (
    "我们有一条底线：文档里写的能力，背后一定有测试或真实执行记录。您问到的任何一点，我都可以"
    "当场指到仓库对应位置。"
)
CLOSER_EN = (
    "Our one constant rule is: if we claim it, a test or a real run backs it. Anything you ask about, "
    "I can point to the exact place in the repository."
)
CHECKLIST_ZH = (
    "1. 重跑一次全量测试，记住最新数字（冻结前记录 220，冻结之后当前实测 230，如再变动按实更新）。\n"
    "2. 本稿全部用「冻结之前 → 冻结之后更新」的句式区分冻结前后，保持口径一致。\n"
    "3. 归因表与官网最终版核对后再上台。"
)
CHECKLIST_EN = (
    "1. Re-run the full test suite and memorize the current number (220 pre-freeze record, 230 measured "
    "after the post-freeze updates; adjust if it changes).\n"
    "2. Keep the freeze-vs-post-freeze wording consistent everywhere.\n"
    "3. Re-check the Attributions Form against the wiki before going on stage."
)

NOTICE_ZH = (
    "表述约定：iGEM 仓库冻结日为 2026-10-21。本聊天内对代码、测试、文档所做的全部改动都发生在冻结"
    "之后，答辩中统一表述为「在冻结之后的更新」。全文不引用任何文件名；如评委追问证据，口头指向"
    "仓库对应位置即可。"
)


def build_print():
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    para(doc, "iGEM 评委现场答辩 Q&A（打印版）", style="Title", size=20, bold=True)
    para(doc, "BioAI Agent / DENTAL SHIELD · LZU-GANSU", size=11, bold=True, color=(0x59, 0x66, 0x80))
    para(doc, NOTICE_ZH, size=9, color=(0x88, 0x55, 0x00))
    doc.add_paragraph()

    para(doc, "Tier 1 —— 高概率（几乎必问）", style="Heading 1")
    for q, variants, zh, en in QUESTIONS[:9]:
        add_question(doc, q, variants, zh, en)
        doc.add_paragraph()

    para(doc, "Tier 2 —— 中低概率（补充 / 压力题）", style="Heading 1")
    for q, variants, zh, en in QUESTIONS[9:]:
        add_question(doc, q, variants, zh, en)
        doc.add_paragraph()

    para(doc, "附：万能收尾（被追问时的安全回答）", style="Heading 1")
    para(doc, "中文：" + CLOSER_ZH)
    para(doc, "English: " + CLOSER_EN)
    doc.add_paragraph()
    para(doc, "上台前复核", style="Heading 1")
    para(doc, CHECKLIST_ZH)

    doc.save("docs/iGEM-Judge-QA-print.docx")


def build_card():
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)
    style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")

    para(doc, "iGEM Judge Q&A — English Cheat Card", style="Title", size=18, bold=True)
    para(doc, "BioAI Agent / DENTAL SHIELD · On-stage answers only", size=10.5, bold=True, color=(0x59, 0x66, 0x80))
    doc.add_paragraph()

    english_titles = [
        "Q1. What is the software, who is it for?",
        "Q2. How does it serve DENTAL SHIELD?",
        "Q3. How do you stop LLM hallucination?",
        "Q4. Do the timeout guardrails really stop?",
        "Q5. Difference vs ChatGPT / Galaxy?",
        "Q6. Data, privacy, Responsible AI?",
        "Q7. Engineering success / DBTL evidence?",
        "Q8. How to install and reproduce?",
        "Q9. Architecture trade-offs?",
        "Q10. Are parallel / racing / recovery real?",
        "Q11. Who actually used it?",
        "Q12. Safety and biosecurity?",
        "Q13. Attribution — who did what?",
        "Q14. Next steps / long-term impact?",
        "Q15. Isn't this just an LLM wrapper?",
    ]

    para(doc, "Tier 1 — High probability", style="Heading 1")
    for title, (_, _, _, en) in zip(english_titles[:9], QUESTIONS[:9]):
        para(doc, title, style="Heading 2")
        para(doc, en)
        doc.add_paragraph()

    para(doc, "Tier 2 — Lower probability / pressure", style="Heading 1")
    for title, (_, _, _, en) in zip(english_titles[9:], QUESTIONS[9:]):
        para(doc, title, style="Heading 2")
        para(doc, en)
        doc.add_paragraph()

    para(doc, "Universal closer", style="Heading 1")
    para(doc, CLOSER_EN)
    doc.add_paragraph()
    para(doc, "Before stage", style="Heading 1")
    para(doc, CHECKLIST_EN)

    doc.save("docs/iGEM-Judge-English-cheatsheet.docx")


if __name__ == "__main__":
    build_print()
    build_card()
    print("OK: two docx files written")
