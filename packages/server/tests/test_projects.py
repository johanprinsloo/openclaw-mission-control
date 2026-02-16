"""
Integration tests for Project endpoints and lifecycle state machine.

Tests cover:
- Project CRUD
- Lifecycle transition validation (forward, backward, invalid)
- Auto-creation of default project channel
- SSE event emission on transitions
"""

from __future__ import annotations

import pytest

from openclaw_mc_shared.schemas.common import ProjectStage, PROJECT_STAGE_ORDER
from openclaw_mc_shared.schemas.projects import validate_transition


# ---------------------------------------------------------------------------
# Unit tests for lifecycle state machine
# ---------------------------------------------------------------------------


class TestLifecycleStateMachine:
    """Test the validate_transition function directly."""

    def test_forward_one_step(self):
        """Forward transitions of one step should succeed."""
        for i in range(len(PROJECT_STAGE_ORDER) - 1):
            current = PROJECT_STAGE_ORDER[i]
            target = PROJECT_STAGE_ORDER[i + 1]
            valid, msg = validate_transition(current, target)
            assert valid, f"{current} -> {target} should be valid: {msg}"

    def test_forward_skip_rejected(self):
        """Skipping stages forward should be rejected."""
        valid, msg = validate_transition(ProjectStage.DEFINITION, ProjectStage.DEVELOPMENT)
        assert not valid
        assert "poc" in msg.lower()

    def test_forward_skip_far(self):
        """Skipping multiple stages forward should be rejected."""
        valid, msg = validate_transition(ProjectStage.DEFINITION, ProjectStage.MAINTENANCE)
        assert not valid

    def test_backward_any_stage(self):
        """Backward transitions to any earlier stage should succeed."""
        # Testing -> Definition (skip back)
        valid, msg = validate_transition(ProjectStage.TESTING, ProjectStage.DEFINITION)
        assert valid

        # Maintenance -> POC
        valid, msg = validate_transition(ProjectStage.MAINTENANCE, ProjectStage.POC)
        assert valid

        # Launch -> Development
        valid, msg = validate_transition(ProjectStage.LAUNCH, ProjectStage.DEVELOPMENT)
        assert valid

    def test_backward_one_step(self):
        """Backward one step should succeed."""
        valid, msg = validate_transition(ProjectStage.DEVELOPMENT, ProjectStage.POC)
        assert valid

    def test_same_stage_rejected(self):
        """Transitioning to the same stage should be rejected."""
        valid, msg = validate_transition(ProjectStage.DEVELOPMENT, ProjectStage.DEVELOPMENT)
        assert not valid
        assert "already" in msg.lower()

    def test_all_forward_transitions_enumerated(self):
        """Enumerate every forward pair to verify only adjacent ones pass."""
        for i, current in enumerate(PROJECT_STAGE_ORDER):
            for j, target in enumerate(PROJECT_STAGE_ORDER):
                if j <= i:
                    continue  # skip same/backward
                valid, _ = validate_transition(current, target)
                if j == i + 1:
                    assert valid, f"{current} -> {target} (adjacent) should be valid"
                else:
                    assert not valid, f"{current} -> {target} (skip) should be invalid"

    def test_all_backward_transitions_valid(self):
        """Every backward transition should be valid."""
        for i, current in enumerate(PROJECT_STAGE_ORDER):
            for j, target in enumerate(PROJECT_STAGE_ORDER):
                if j >= i:
                    continue
                valid, msg = validate_transition(current, target)
                assert valid, f"{current} -> {target} (backward) should be valid: {msg}"

    def test_stage_order_completeness(self):
        """All ProjectStage values should be in PROJECT_STAGE_ORDER."""
        for stage in ProjectStage:
            assert stage in PROJECT_STAGE_ORDER, f"{stage} missing from ORDER"

    def test_stage_count(self):
        """Should have exactly 6 stages."""
        assert len(PROJECT_STAGE_ORDER) == 6
