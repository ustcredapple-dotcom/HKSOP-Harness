"""Load the published PM-532 graph as the test fixture (one authoring source)."""
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
_spec = spec_from_file_location("pm532_published", Path(__file__).resolve().parents[1] / "examples/pm-fiber-1x3-532/graph.py")
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
build_graph = _module.build_graph
