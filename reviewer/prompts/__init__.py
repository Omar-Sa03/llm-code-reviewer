"""Prompt definitions package — versioned so A/B comparisons are reproducible."""
from __future__ import annotations

from reviewer.prompts.v1 import SYSTEM_PROMPT as _V1_SYSTEM
from reviewer.prompts.v1 import build_prompt as _v1_build
from reviewer.prompts.v2 import SYSTEM_PROMPT as _V2_SYSTEM
from reviewer.prompts.v2 import build_prompt as _v2_build

_VERSIONS = {
    "v1": (_V1_SYSTEM, _v1_build),
    "v2": (_V2_SYSTEM, _v2_build),
}


def get_prompt(version: str = "v2") -> tuple[str, object]:
    """
    Return (system_prompt, build_prompt_fn) for the requested version.

    Falls back to v2 for unknown versions and logs a warning.
    """
    if version not in _VERSIONS:
        import logging
        logging.getLogger(__name__).warning(
            "Unknown prompt version %r — falling back to v2", version
        )
        version = "v2"
    return _VERSIONS[version]
