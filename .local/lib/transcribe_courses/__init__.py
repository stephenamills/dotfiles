"""Standalone course-transcription package with a compatibility facade."""

from __future__ import annotations

import sys
from types import ModuleType

from . import config, models, state, worker, discovery, media, pipeline, cli


_MODULES = (config, models, state, worker, discovery, media, pipeline, cli)

# Give unittest.mock a local slot for each compatibility export. Attribute
# reads below still resolve against the owning modules so mutable runtime state
# never becomes stale in this facade.
for _module in _MODULES:
    for _name, _value in vars(_module).items():
        globals().setdefault(_name, _value)


class _PackageFacade(ModuleType):
    """Route legacy attribute patches to the modules that own those names.

    The original test suite and a few local callers imported one script module.
    Keeping this small facade makes that API compatible while production code
    remains split by responsibility.
    """

    def __getattribute__(self, name: str) -> object:
        if name in {
            "_MODULES",
            "__class__",
            "__dict__",
            "__name__",
            "__spec__",
            "__loader__",
            "__package__",
            "__path__",
        }:
            return super().__getattribute__(name)
        modules = super().__getattribute__("_MODULES")
        for module in reversed(modules):
            if hasattr(module, name):
                return getattr(module, name)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: object) -> None:
        matched = False
        for module in _MODULES:
            if hasattr(module, name):
                setattr(module, name, value)
                matched = True
        if not matched:
            super().__setattr__(name, value)

    def __dir__(self) -> list[str]:
        return sorted(
            set(super().__dir__()).union(
                *(vars(module).keys() for module in _MODULES)
            )
        )


sys.modules[__name__].__class__ = _PackageFacade

__all__ = [
    name
    for name in dir(sys.modules[__name__])
    if not name.startswith("_")
]
