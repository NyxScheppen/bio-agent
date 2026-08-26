import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bioagent.api import router
from bioagent.config import Config, load_config
from bioagent.db import connect
from bioagent.llm.client import LlmClient
from bioagent.orchestration.graph import build_graph
from bioagent.r_runner import RRunner
from bioagent.rag import Embedder, RagClient
from bioagent.tools import ToolRegistry

log = logging.getLogger(__name__)


def create_app(config: Config | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        cfg = config or load_config()  # 延迟到启动时读，测试可注入
        db = await connect(cfg.db.db_path)
        client = LlmClient.from_config(cfg.llm, db)
        registry = ToolRegistry()
        registry.discover()
        runner = RRunner(cfg.storage.r_scripts_dir)
        embedder = Embedder(cfg.embedding.model)
        rag = RagClient(embedder, cfg.rag.qdrant_url, cfg.rag.collection, cfg.rag.top_k)
        await rag.ensure_collection()
        graph = build_graph(
            client, registry, runner, db,
            cfg.eval.judge_sample_rate, cfg.storage.upload_dir, rag,
        )
        app.state.cfg = cfg
        app.state.db = db
        app.state.registry = registry
        app.state.graph = graph
        log.info("bioagent ready: %d tools", len(registry))
        yield
        await rag.close()
        await db.conn.close()

    app = FastAPI(title="bioagent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # 开发期放开；上线收紧为白名单
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()  # 生产入口：uvicorn bioagent.main:app
