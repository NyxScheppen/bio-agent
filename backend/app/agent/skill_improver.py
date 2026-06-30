"""
技能自改进反馈循环 (Phase 4.4: Self-Improvement).

参考 Hermes agent 的自主 Skill 创建和自改进机制。

功能:
1. 记录工具有执行失败模式
2. 定期分析失败模式 → 输出改进建议
3. 写入 improvement_suggestions.json 供人工审核
4. 不自修改 Skill（安全第一）

用法:
    from app.agent.skill_improver import record_failure, analyze_and_suggest
    record_failure(tool_name="run_survival", error_pattern="missing column")
    # ... 积累数据后 ...
    suggestions = analyze_and_suggest()
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.runtime_paths import PROJECT_ROOT

IMPROVEMENT_LOG_DIR = PROJECT_ROOT / "logs" / "improvements"
IMPROVEMENT_LOG_FILE = IMPROVEMENT_LOG_DIR / "failure_patterns.jsonl"
SUGGESTIONS_FILE = IMPROVEMENT_LOG_DIR / "improvement_suggestions.json"
MAX_LOG_ENTRIES = 10000  # 最多保留条目，防止文件无限增长


def _ensure_log_dir():
    """确保日志目录存在。"""
    IMPROVEMENT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def record_failure(
    tool_name: str,
    error_pattern: str,
    session_id: str = "",
    job_id: str = "",
    extra: Optional[Dict[str, Any]] = None,
):
    """
    记录一次工具有失败，用于后续分析。

    Args:
        tool_name: 工具名
        error_pattern: 错误描述（简短关键词，如 "missing column", "timeout"）
        session_id: 会话 ID（可选）
        job_id: 任务 ID（可选）
        extra: 额外上下文（可选）
    """
    try:
        _ensure_log_dir()

        entry = {
            "timestamp": datetime.now().isoformat(),
            "tool_name": tool_name,
            "error_pattern": error_pattern,
            "session_id": session_id or "",
            "job_id": job_id or "",
            "extra": extra or {},
        }

        # 追加写入
        with open(IMPROVEMENT_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # 定期裁剪
        _trim_log_if_needed()

    except Exception:
        pass  # 静默失败


def _trim_log_if_needed():
    """如果日志过大，保留最新的条目。"""
    try:
        if not IMPROVEMENT_LOG_FILE.exists():
            return

        with open(IMPROVEMENT_LOG_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if len(lines) > MAX_LOG_ENTRIES:
            with open(IMPROVEMENT_LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-MAX_LOG_ENTRIES:])
    except Exception:
        pass


def analyze_and_suggest() -> List[Dict[str, Any]]:
    """
    分析失败日志，生成改进建议。

    Returns:
        建议列表，每条包含:
        {
            "type": "clarification_rule" | "recovery_strategy" | "parameter_rule" | "new_skill",
            "priority": "high" | "medium" | "low",
            "tool_name": "...",
            "description": "...",
            "suggested_action": "..."
        }
    """
    _ensure_log_dir()

    if not IMPROVEMENT_LOG_FILE.exists():
        return []

    try:
        entries = []
        with open(IMPROVEMENT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except Exception:
        return []

    if len(entries) < 10:
        return []  # 数据不够，不做分析

    suggestions: List[Dict[str, Any]] = []

    # 分析 1: 高频失败工具 → 建议添加 recovery_strategy
    tool_failures: Dict[str, int] = defaultdict(int)
    for e in entries:
        tool_failures[e["tool_name"]] += 1

    for tool, count in tool_failures.items():
        if count >= 3:
            suggestions.append({
                "type": "recovery_strategy",
                "priority": "high" if count >= 10 else "medium",
                "tool_name": tool,
                "description": f"工具 `{tool}` 最近失败 {count} 次",
                "suggested_action": f"为 `{tool}` 编写专用 RecoveryStrategy 或改进参数验证",
            })

    # 分析 2: 高频错误模式 → 建议添加 clarification_rule
    pattern_counts: Dict[str, int] = defaultdict(int)
    pattern_tools: Dict[str, set] = defaultdict(set)
    for e in entries:
        pattern = e.get("error_pattern", "")
        if pattern:
            pattern_counts[pattern] += 1
            pattern_tools[pattern].add(e["tool_name"])

    for pattern, count in pattern_counts.items():
        if count >= 5:
            affected = ", ".join(sorted(pattern_tools[pattern])[:5])
            suggestions.append({
                "type": "clarification_rule",
                "priority": "high" if count >= 20 else "medium",
                "tool_name": affected,
                "description": f"错误模式 `{pattern}` 出现 {count} 次，影响 {len(pattern_tools[pattern])} 个工具",
                "suggested_action": f"在 Skill 中添加 clarification_rule，提前追问用户避免 `{pattern}` 错误",
            })

    # 分析 3: 检查是否缺少 skill
    all_affected_tools = set()
    for e in entries:
        all_affected_tools.add(e["tool_name"])

    if len(all_affected_tools) >= 5:
        suggestions.append({
            "type": "new_skill",
            "priority": "low",
            "tool_name": ", ".join(sorted(all_affected_tools)[:5]),
            "description": f"多个工具 ({len(all_affected_tools)}) 出现失败模式",
            "suggested_action": "考虑创建涵盖这些工具的 Skill，统一参数验证和错误处理",
        })

    # 写入建议文件
    try:
        output = {
            "generated_at": datetime.now().isoformat(),
            "total_entries_analyzed": len(entries),
            "suggestions": suggestions,
        }
        with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return suggestions


def clear_logs():
    """清空失败日志（用于重新开始统计）。"""
    _ensure_log_dir()
    try:
        if IMPROVEMENT_LOG_FILE.exists():
            IMPROVEMENT_LOG_FILE.unlink()
        if SUGGESTIONS_FILE.exists():
            SUGGESTIONS_FILE.unlink()
    except Exception:
        pass


def get_stats() -> Dict[str, Any]:
    """获取当前统计数据摘要。"""
    _ensure_log_dir()

    if not IMPROVEMENT_LOG_FILE.exists():
        return {"total_entries": 0, "tools": {}, "patterns": {}}

    try:
        entries = []
        with open(IMPROVEMENT_LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        tool_counts: Dict[str, int] = defaultdict(int)
        pattern_counts: Dict[str, int] = defaultdict(int)
        for e in entries:
            tool_counts[e["tool_name"]] += 1
            pattern = e.get("error_pattern", "")
            if pattern:
                pattern_counts[pattern] += 1

        return {
            "total_entries": len(entries),
            "tools": dict(tool_counts),
            "patterns": dict(pattern_counts),
        }
    except Exception:
        return {"total_entries": 0, "tools": {}, "patterns": {}}
