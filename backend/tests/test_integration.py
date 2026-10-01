"""Quick integration test for Phase 1: ToolResult."""
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent.tool_result import make_success_result, normalize_tool_result
from app.agent.agent_utils import extract_output_files, build_compact_tool_summary

# Test 1: extract_output_files with ToolResult
tr = make_success_result(
    message="test",
    output_files=[
        {"name": "a.csv", "url": "/files/g/a.csv"},
        {"name": "b.png", "url": "/files/g/b.png"},
    ],
)
files = extract_output_files(tr)
assert len(files) == 2, f"Expected 2 files, got {len(files)}"
assert files[0]["name"] == "a.csv"
print("[PASS] extract_output_files from ToolResult")

# Test 2: extract_output_files with old dict
old = {"status": "success", "output_files": [{"name": "old.csv", "url": "/files/old.csv"}]}
old_files = extract_output_files(old)
assert len(old_files) == 1
assert old_files[0]["name"] == "old.csv"
print("[PASS] extract_output_files from old dict")

# Test 3: build_compact_tool_summary with ToolResult
summary = build_compact_tool_summary(tr)
assert "success" in summary
print("[PASS] build_compact_tool_summary with ToolResult")

# Test 4: normalize from old error dict
old_error = {"status": "error", "message": "R crash", "stderr": "segfault"}
nr = normalize_tool_result(old_error, tool_name="r_tool")
assert nr.status == "error"
assert len(nr.errors) > 0
print("[PASS] normalize_tool_result error flows through to agent_utils")

# Test 5: Legacy dict round-trip
from app.agent.tool_result import tool_result_to_legacy_dict

tr2 = make_success_result(message="OK", warnings=["small sample"])
legacy = tool_result_to_legacy_dict(tr2)
assert legacy["status"] == "success"
assert legacy["warnings"] == ["small sample"]
files_from_legacy = extract_output_files(legacy)
assert len(files_from_legacy) == 0  # no output_files in this tr2
print("[PASS] legacy dict round-trip")

print("\nAll integration tests passed!")
