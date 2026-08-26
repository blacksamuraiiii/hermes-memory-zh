"""Shared pytest config.

The plugin repo root IS the plugin package (it ships __init__.py as the
provider entry), so `from . import holographic` works in the installed context
but not when pytest imports store.py standalone. We preload the pure-logic
modules (holographic / store / retrieval) as top-level modules from their file
paths; tests then `from store import MemoryStore` directly.

store.py's _init_db lazily imports hermes_state, so a hermes-agent checkout is
also put on sys.path. Point HERMES_AGENT_PATH at it if it isn't at
~/.hermes/hermes-agent. Tokenize-only tests don't need hermes core.
"""
import importlib.util
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _load_as_top_level(name: str) -> None:
    """Load <name>.py from the repo root under a plain top-level module name."""
    path = _ROOT / f"{name}.py"
    if not path.exists():
        return
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)


for _m in ("holographic", "store", "retrieval"):
    _load_as_top_level(_m)

# hermes-agent source tree (store._init_db imports hermes_state / hermes_constants).
_HERMES = os.environ.get(
    "HERMES_AGENT_PATH", str(Path.home() / ".hermes" / "hermes-agent")
)
if Path(_HERMES).exists() and str(_HERMES) not in sys.path:
    sys.path.insert(0, _HERMES)

# Keep the repo root on path too (future embedding.py / any direct imports).
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
