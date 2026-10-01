# Third-Party Notices

BioAI Agent is distributed under the MIT License, but it depends on third-party software with independent licenses and citation requirements.

Major runtime ecosystems include:

- FastAPI, Starlette, Uvicorn, SQLAlchemy, Pydantic, OpenAI's Python client, pandas, NumPy, SciPy, scikit-learn, Matplotlib, Seaborn, NetworkX, and their transitive Python dependencies.
- React, React DOM, Vite, TypeScript, Lucide, React Markdown, remark-gfm, Vitest, ESLint, and their transitive npm dependencies.
- R, Bioconductor, Seurat, DESeq2, limma, clusterProfiler, GSVA, glmnet, survival, survminer, caret, and the other packages resolved in `renv.lock`.

The authoritative package names and versions are recorded in `requirements.txt`, `frontend/package-lock.json`, and `renv.lock`. Each package retains the copyright, license, and citation terms published by its maintainers. Generated analyses should cite the scientific methods and databases they use, including applicable Bioconductor packages, MSigDB, KEGG, STRING, Europe PMC, and organism annotation databases.

This notice is a high-level index, not a replacement for the license metadata shipped by each dependency. Before binary redistribution, generate and review a complete dependency license inventory for the target build.
