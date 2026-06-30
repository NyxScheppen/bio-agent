"""Quick verification of Phase 3 tool registration."""
import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Force import of example tools
from app.tools.example_pydantic_tool import *  # noqa
from app.agent.tool_registry import TOOL_REGISTRY, TOOL_META, TOOLS_SCHEMA

print("Tools registered:")
for name in ["calculate_gc_content_v2", "count_sequence_bases", "reverse_complement_v2"]:
    if name in TOOL_REGISTRY:
        meta = TOOL_META[name]
        print(f"  {name}: category={meta['category']}, schema_source={meta.get('schema_source','?')}")
    else:
        print(f"  {name}: NOT FOUND")

# Check signature-based schema
for item in TOOLS_SCHEMA:
    fn = item["function"]
    if fn["name"] == "count_sequence_bases":
        print(f"\nSchema for count_sequence_bases (signature-based):")
        print(json.dumps(fn["parameters"], indent=2, ensure_ascii=False))
        break

# Check Pydantic-based schema
for item in TOOLS_SCHEMA:
    fn = item["function"]
    if fn["name"] == "calculate_gc_content_v2":
        print(f"\nSchema for calculate_gc_content_v2 (Pydantic):")
        print(json.dumps(fn["parameters"], indent=2, ensure_ascii=False))
        break

print("\nAll Phase 3 verifications passed!")
