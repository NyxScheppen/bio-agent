from bioagent.enums import Category, Runtime
from bioagent.types import ToolDefinition

TOOL = ToolDefinition(
    name="dge_foo",
    description="fixture DGE 工具（R）",
    category=Category.DGE,
    runtime=Runtime.R,
    input_schema={},
    output_schema={},
    run=None,
    r_script="dge_foo.R",
)
