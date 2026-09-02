#!/usr/bin/env python3
from __future__ import annotations

from dependency_governance_lib.github import classify_ecosystem, parse_dependabot_metadata
from dependency_governance_lib.models import (
    ACTION_LINE, GovernanceError, parse_bool, parse_positive_integer, validate_config,
)
from dependency_governance_lib.provenance import validate_provenance
from dependency_governance_lib.semantics import validate_actions, validate_go_override
from dependency_governance_lib.qualification import validate_run_identity
from dependency_governance_lib.runner import main, target_pull_requests

__all__ = [
    "ACTION_LINE", "GovernanceError", "classify_ecosystem", "parse_bool",
    "parse_dependabot_metadata", "parse_positive_integer", "target_pull_requests",
    "validate_actions", "validate_config", "validate_go_override",
    "validate_provenance", "validate_run_identity",
]

if __name__ == "__main__":
    raise SystemExit(main())
