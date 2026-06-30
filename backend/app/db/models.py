from sqlalchemy import Column, Integer, String, Text, DateTime, Float
from sqlalchemy.sql import func
from app.db.database import Base

class ChatSession(Base):
    """
    会话表：一条记录代表一次会话
    """
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, unique=True, index=True, nullable=False)
    title = Column(String, default="新会话")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ChatMessage(Base):
    """
    消息表：存每轮 user / assistant 对话内容
    """
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=False)
    role = Column(String, nullable=False)   # user / assistant / system
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class StoredFile(Base):
    """
    文件表：记录上传文件和生成文件
    """
    __tablename__ = "stored_files"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=True)
    filename = Column(String, nullable=False)
    relative_path = Column(String, nullable=False)  # 如 uploads/test.csv 或 generated/plot.png
    file_type = Column(String, nullable=False)      # image / table / text / other
    source_type = Column(String, nullable=False)    # upload / generated
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ToolExecution(Base):
    """
    工具执行审计日志表 (Feature 2: Audit Logs)

    每次工具调用写入一条记录，持久化 ToolProvenance 和 ToolResult 关键字段。
    JSON 字段用于存储结构化数据（parameters, errors, output_files 等）。
    """
    __tablename__ = "tool_executions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True, nullable=True)
    job_id = Column(String, index=True, nullable=False)
    workflow_id = Column(String, nullable=True)
    tool_name = Column(String, index=True, nullable=False)
    tool_category = Column(String, nullable=False, default="general")
    status = Column(String, nullable=False, default="success")  # success / error / partial
    parameters_json = Column(Text, nullable=True)     # JSON: 工具调用参数
    started_at = Column(String, nullable=True)        # ISO 8601
    finished_at = Column(String, nullable=True)       # ISO 8601
    runtime_seconds = Column(Float, nullable=True)
    message = Column(Text, nullable=True)             # 结果描述
    errors_json = Column(Text, nullable=True)         # JSON: 错误列表
    warnings_json = Column(Text, nullable=True)       # JSON: 警告列表
    output_files_json = Column(Text, nullable=True)   # JSON: 输出文件列表
    resource_usage_json = Column(Text, nullable=True) # JSON: ResourceUsage
    retry_count = Column(Integer, default=0)
    recovery_attempts_json = Column(Text, nullable=True)  # JSON: RetryRecord 列表
    created_at = Column(DateTime(timezone=True), server_default=func.now())