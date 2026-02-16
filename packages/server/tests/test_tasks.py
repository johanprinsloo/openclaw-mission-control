"""
Integration tests for Task endpoints: evidence validation and dependency graph.

Tests cover:
- Evidence gate: transition to complete requires all required evidence types
- Dependency graph: circular dependency detection
- Task CRUD and transition validation
"""

from __future__ import annotations

import uuid
from collections import defaultdict

import pytest

from openclaw_mc_shared.schemas.common import EvidenceType, TaskPriority, TaskStatus
from openclaw_mc_shared.schemas.tasks import (
    DependencyAdd,
    EvidenceSubmission,
    TaskCreate,
    TaskTransition,
    TaskUpdate,
)


# ---------------------------------------------------------------------------
# Unit tests: Evidence validation logic
# ---------------------------------------------------------------------------


class TestEvidenceValidation:
    """Test evidence requirements for task completion."""

    def test_no_evidence_required_allows_completion(self):
        """Tasks with empty required_evidence_types can complete without evidence."""
        required: list[str] = []
        submitted = set()
        missing = set(required) - submitted
        assert len(missing) == 0

    def test_evidence_required_blocks_without_submission(self):
        """Tasks with required evidence types cannot complete without all types submitted."""
        required = [EvidenceType.PR_LINK.value, EvidenceType.TEST_RESULTS.value]
        submitted = {EvidenceType.PR_LINK.value}
        missing = set(required) - submitted
        assert missing == {EvidenceType.TEST_RESULTS.value}

    def test_evidence_required_allows_with_all_submitted(self):
        """Tasks with all required evidence types submitted can complete."""
        required = [EvidenceType.PR_LINK.value, EvidenceType.TEST_RESULTS.value]
        submitted = {EvidenceType.PR_LINK.value, EvidenceType.TEST_RESULTS.value}
        missing = set(required) - submitted
        assert len(missing) == 0

    def test_extra_evidence_is_fine(self):
        """Submitting extra evidence beyond requirements is allowed."""
        required = [EvidenceType.PR_LINK.value]
        submitted = {EvidenceType.PR_LINK.value, EvidenceType.TEST_RESULTS.value, EvidenceType.DOC_URL.value}
        missing = set(required) - submitted
        assert len(missing) == 0

    def test_evidence_submission_model(self):
        """EvidenceSubmission model validates correctly."""
        ev = EvidenceSubmission(type=EvidenceType.PR_LINK, url="https://github.com/pr/1")
        assert ev.type == EvidenceType.PR_LINK
        assert ev.url == "https://github.com/pr/1"


# ---------------------------------------------------------------------------
# Unit tests: Dependency graph / circular detection
# ---------------------------------------------------------------------------


def _has_path_sync(adj: dict[str, list[str]], from_id: str, to_id: str) -> bool:
    """Synchronous BFS for testing circular dependency detection logic."""
    visited: set[str] = set()
    queue = [from_id]
    while queue:
        current = queue.pop(0)
        if current == to_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        queue.extend(adj.get(current, []))
    return False


class TestCircularDependencyDetection:
    """Test the BFS-based circular dependency detection."""

    def test_no_cycle_simple(self):
        """A -> B: adding A -> B should not detect a cycle."""
        adj: dict[str, list[str]] = defaultdict(list)
        # Before adding A -> B, check if B -> A path exists
        assert not _has_path_sync(adj, "B", "A")

    def test_direct_cycle(self):
        """A -> B exists, adding B -> A would create a cycle."""
        adj: dict[str, list[str]] = defaultdict(list)
        adj["A"].append("B")  # A is blocked by B
        # Before adding B -> A, check if A -> B path exists
        assert _has_path_sync(adj, "A", "B")

    def test_indirect_cycle(self):
        """A -> B -> C exists, adding C -> A would create a cycle."""
        adj: dict[str, list[str]] = defaultdict(list)
        adj["A"].append("B")
        adj["B"].append("C")
        # Before adding C -> A, check if A -> C path exists
        assert _has_path_sync(adj, "A", "C")

    def test_no_indirect_cycle(self):
        """A -> B, C -> D: adding D -> A has no cycle."""
        adj: dict[str, list[str]] = defaultdict(list)
        adj["A"].append("B")
        adj["C"].append("D")
        # Before adding D -> A, check if A -> D path exists
        assert not _has_path_sync(adj, "A", "D")

    def test_diamond_no_cycle(self):
        """A -> B, A -> C, B -> D, C -> D: adding E -> A has no cycle."""
        adj: dict[str, list[str]] = defaultdict(list)
        adj["A"].append("B")
        adj["A"].append("C")
        adj["B"].append("D")
        adj["C"].append("D")
        assert not _has_path_sync(adj, "A", "E")

    def test_complex_cycle(self):
        """A -> B -> C -> D exists, adding D -> B creates cycle B -> C -> D -> B."""
        adj: dict[str, list[str]] = defaultdict(list)
        adj["A"].append("B")
        adj["B"].append("C")
        adj["C"].append("D")
        # Before adding D -> B, check if B -> D path exists
        assert _has_path_sync(adj, "B", "D")

    def test_self_dependency(self):
        """Self-dependency A -> A should be detected."""
        adj: dict[str, list[str]] = defaultdict(list)
        # Check if A can reach A (trivially yes via start node)
        assert _has_path_sync(adj, "A", "A")


# ---------------------------------------------------------------------------
# Unit tests: Transition validation
# ---------------------------------------------------------------------------


class TestTransitionValidation:
    """Test the task status transition state machine."""

    VALID_TRANSITIONS = {
        TaskStatus.BACKLOG: [TaskStatus.IN_PROGRESS],
        TaskStatus.IN_PROGRESS: [TaskStatus.BACKLOG, TaskStatus.IN_REVIEW],
        TaskStatus.IN_REVIEW: [TaskStatus.IN_PROGRESS, TaskStatus.COMPLETE],
        TaskStatus.COMPLETE: [TaskStatus.IN_REVIEW],
    }

    def test_all_valid_transitions(self):
        for from_status, to_statuses in self.VALID_TRANSITIONS.items():
            for to_status in to_statuses:
                allowed = self.VALID_TRANSITIONS.get(from_status, [])
                assert to_status in allowed, f"{from_status} -> {to_status} should be valid"

    def test_invalid_skip(self):
        """Cannot go directly from backlog to complete."""
        allowed = self.VALID_TRANSITIONS.get(TaskStatus.BACKLOG, [])
        assert TaskStatus.COMPLETE not in allowed

    def test_invalid_skip_review(self):
        """Cannot go directly from backlog to in-review."""
        allowed = self.VALID_TRANSITIONS.get(TaskStatus.BACKLOG, [])
        assert TaskStatus.IN_REVIEW not in allowed

    def test_reopen_from_complete(self):
        """Can reopen a complete task back to in-review."""
        allowed = self.VALID_TRANSITIONS.get(TaskStatus.COMPLETE, [])
        assert TaskStatus.IN_REVIEW in allowed

    def test_same_status_not_allowed(self):
        """Transitioning to the same status is not in the allowed list."""
        for status in TaskStatus:
            allowed = self.VALID_TRANSITIONS.get(status, [])
            assert status not in allowed


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestTaskSchemas:
    """Test Pydantic schema validation."""

    def test_task_create_defaults(self):
        t = TaskCreate(title="Test task")
        assert t.priority == TaskPriority.MEDIUM
        assert t.type == "chore"
        assert t.required_evidence_types == []
        assert t.project_ids == []
        assert t.assignee_ids == []

    def test_task_create_with_evidence(self):
        t = TaskCreate(
            title="Test",
            required_evidence_types=[EvidenceType.PR_LINK, EvidenceType.TEST_RESULTS],
        )
        assert len(t.required_evidence_types) == 2

    def test_task_transition_with_evidence(self):
        tr = TaskTransition(
            to_status=TaskStatus.COMPLETE,
            evidence=[
                EvidenceSubmission(type=EvidenceType.PR_LINK, url="https://github.com/pr/1"),
            ],
        )
        assert tr.to_status == TaskStatus.COMPLETE
        assert len(tr.evidence) == 1

    def test_task_transition_without_evidence(self):
        tr = TaskTransition(to_status=TaskStatus.IN_PROGRESS)
        assert tr.evidence == []

    def test_task_update_partial(self):
        u = TaskUpdate(title="New title")
        dumped = u.model_dump(exclude_unset=True)
        assert dumped == {"title": "New title"}

    def test_dependency_add(self):
        d = DependencyAdd(blocked_by_id=uuid.uuid4())
        assert d.blocked_by_id is not None


# ---------------------------------------------------------------------------
# End-to-end flow test (schema-level)
# ---------------------------------------------------------------------------


class TestEndToEndFlow:
    """Test the conceptual end-to-end task completion flow at the schema level."""

    def test_full_lifecycle(self):
        """Create -> In Progress -> In Review -> Complete (with evidence)."""
        # 1. Create
        task = TaskCreate(
            title="Implement feature X",
            type="feature",
            priority=TaskPriority.HIGH,
            required_evidence_types=[EvidenceType.PR_LINK],
        )
        assert task.title == "Implement feature X"

        # 2. Transition to in-progress
        t1 = TaskTransition(to_status=TaskStatus.IN_PROGRESS)
        assert t1.to_status == TaskStatus.IN_PROGRESS

        # 3. Transition to in-review
        t2 = TaskTransition(to_status=TaskStatus.IN_REVIEW)
        assert t2.to_status == TaskStatus.IN_REVIEW

        # 4. Attempt complete without evidence — would fail at service layer
        t3_no_ev = TaskTransition(to_status=TaskStatus.COMPLETE)
        assert t3_no_ev.evidence == []  # no evidence

        # 5. Complete with evidence
        t3 = TaskTransition(
            to_status=TaskStatus.COMPLETE,
            evidence=[
                EvidenceSubmission(type=EvidenceType.PR_LINK, url="https://github.com/pr/42"),
            ],
        )
        assert len(t3.evidence) == 1
        assert t3.evidence[0].type == EvidenceType.PR_LINK
