# BioAI Agent

BioAI Agent is an open-source, local-first assistant for reproducible bioinformatics workflows. It combines a FastAPI application, a multi-agent planner/executor, declarative YAML Skills, Python and R analysis tools, and a React web interface.

This project is the open-source software deliverable of
[iGEM 2026 Team LZU GANSU](https://2026.igem.wiki/lzu-gansu) from Lanzhou University.
The official software repository is
[2026/software/lzu-gansu/bio-agent](https://gitlab.igem.org/2026/software/lzu-gansu/bio-agent).

[Chinese README](README.md) | [iGEM submission guide](docs/IGEM_SUBMISSION.md) | [Behavior verification](docs/README_FEATURE_VERIFICATION.md)

![BioAI Agent workspace interface](docs/assets/bioai-agent-interface.png)

## What is implemented

- Multi-agent routing, planning, delegated execution, reporting, dependency-aware parallelism, retries, timeouts, and tool-policy enforcement.
- 54 declarative Skills across 16 YAML packs. The runtime distinguishes implemented, partial, and planned workflows before execution.
- 40 registered tools for transcriptomics, survival analysis, enrichment, machine learning, literature search, network pharmacology, file inspection, single-cell RNA-seq, spatial transcriptomics, and perturbation-response analysis.
- Session-scoped uploads, generated artifacts, conversation history, downloadable figures, and structured result metadata.
- A same-origin React/TypeScript frontend whose complete source and lockfile are included in `frontend/`.

The exact tested scope and known boundaries are recorded in [docs/README_FEATURE_VERIFICATION.md](docs/README_FEATURE_VERIFICATION.md). In particular, the virtual knockdown scenario is a deterministic expression-scaling experiment, not a learned causal perturbation model. Planned workflows stop before tool execution and are not reported as complete.

## Architecture

```text
React/Vite frontend
       |
       | /api/chat, /api/upload, /api/history, /files
       v
FastAPI service
       |
       +-- Router -> Skill selection -> Planner
       |                    |
       |                    +-- Delegator / Orchestrator
       |                              |
       |                              +-- policy-bound Python and R tools
       |
       +-- Reporter -> reply + generated artifacts
       |
       +-- SQLite metadata + session-scoped storage
```

## Requirements

- Python 3.11 or 3.12
- R 4.2 or newer for R-backed workflows
- Node.js 22 or newer to rebuild the frontend
- Windows 10/11 for the supported one-click launcher

The backend itself is mostly portable, but the repository currently guarantees the launcher and complete analysis environment on Windows. The GitLab pipeline validates Python and frontend code on Linux; it does not claim that every external R/Bioconductor workflow is installed or executed in CI.

## Reproduce the application

### 1. Configure Python

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

On POSIX systems, replace `.venv\Scripts\python.exe` with `.venv/bin/python`.

### 2. Configure the model provider

```powershell
Copy-Item backend\.env_example backend\.env
```

Set `DEEPSEEK_API_KEY` in `backend/.env`. Never commit that file. The model endpoint and model name can be changed through `DEEPSEEK_BASE_URL` and `MODEL_NAME`.

### 3. Install R dependencies

For the complete supported Windows setup:

```powershell
Rscript install_r_packages.R
```

`renv.lock` records the resolved R dependency set used by the project. Contributors can restore it with `renv::restore(lockfile = "renv.lock")`; the application launcher uses the repository-private `env/r_libs` library created by `install_r_packages.R`.

### 4. Rebuild the frontend

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
Set-Location ..
```

The production build is written to `backend/static/`. Browser requests use relative `/api` and `/files` URLs, so no developer host is embedded in the production bundle.

### 5. Run

On Windows, `start_app.bat` checks the environment, installs missing Python dependencies, starts FastAPI, and opens the browser. A direct backend launch is:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. Confirm the service with `GET /api/health`.

## Verification

```powershell
.venv\Scripts\python.exe -m compileall -q backend/app
.venv\Scripts\python.exe -m pytest -q backend/tests
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts/verify_submission.py
```

The same checks, plus the frontend lint/typecheck/test/build sequence, run in `.gitlab-ci.yml`. Tests that require paid model calls or unstable external biological databases are intentionally excluded from CI; their latest manual evidence and failures are documented rather than silently counted as passes.

## Data and security boundaries

- Uploads and generated data are runtime artifacts under the backend storage directory and are excluded from version control.
- File names, archive expansion, storage paths, remote downloads, and generated artifacts are constrained by explicit validation and resource budgets.
- Arbitrary R execution is restricted and should still be treated as high-risk functionality. Deploy the service for trusted users, bind it to a private interface, and do not expose it directly to the public internet.
- Biological outputs are research aids, not clinical advice. Validate important conclusions with domain experts and independent methods.

See [docs/file-artifact-behavior.md](docs/file-artifact-behavior.md), [docs/multi-agent-behavior.md](docs/multi-agent-behavior.md), and [docs/skill_tool_prompt_behavior.md](docs/skill_tool_prompt_behavior.md) for behavioral contracts.

## Contributing and citation

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow. The final member contribution statement, archive DOI, and preferred citation will be added by the team before the repository freeze.

## iGEM team

- **Team:** iGEM 2026 Team LZU GANSU
- **Institution:** Lanzhou University
- **Official team slug:** `lzu-gansu`
- **Team wiki:** [https://2026.igem.wiki/lzu-gansu](https://2026.igem.wiki/lzu-gansu)
- **iGEM GitLab wiki project:** [https://gitlab.igem.org/2026/lzu-gansu](https://gitlab.igem.org/2026/lzu-gansu)
- **iGEM software repository:** [https://gitlab.igem.org/2026/software/lzu-gansu/bio-agent](https://gitlab.igem.org/2026/software/lzu-gansu/bio-agent)
- **Full development-history mirror:** [https://github.com/NyxScheppen/bio-agent](https://github.com/NyxScheppen/bio-agent)
- **Responsible AI guidance:** [.claude/RESPONSIBLE_AI_USE.md](.claude/RESPONSIBLE_AI_USE.md)

Individual contributions and supervisor credits are maintained in the final Attributions Form and team wiki.

## License

BioAI Agent is released under the [MIT License](LICENSE). Third-party packages retain their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
