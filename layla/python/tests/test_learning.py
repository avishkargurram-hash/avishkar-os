import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.audit import AuditLogger
from avishkar_layla.learning import LearningLoop
from avishkar_layla.session import SessionManager
from avishkar_layla.skills import SKILL_CANDIDATE, SkillRegistry
from avishkar_layla.types import COMPLETED, Plan, PlanStep, LaylaTask


def _setup(min_occurrences=3):
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    sessions = SessionManager(memory)
    audit = AuditLogger(memory)
    skills = SkillRegistry(memory)
    loop = LearningLoop(sessions, audit, skills, min_occurrences=min_occurrences)
    return loop, sessions, audit, skills


def _completed_task_with_delegation(sessions, audit, task_id, capability):
    plan = Plan(id=f"plan-{task_id}", task_id=task_id, steps=(
        PlanStep(id=f"step-{task_id}", required_capability=capability, input="x"),
    ))
    task = LaylaTask(input="x", id=task_id, state=COMPLETED, plan=plan, plan_id=plan.id)
    sessions.save(task)
    audit.record("layla.delegation.completed", {"step_id": f"step-{task_id}"}, task_id=task_id)
    return task


class TestLearningLoopExtractCandidates(unittest.TestCase):
    def test_below_threshold_produces_no_candidates(self):
        loop, sessions, audit, skills = _setup(min_occurrences=3)
        _completed_task_with_delegation(sessions, audit, "t1", "finance-agent")
        _completed_task_with_delegation(sessions, audit, "t2", "finance-agent")

        suggestions = loop.extract_candidate_skills()

        self.assertEqual(suggestions, ())
        self.assertEqual(skills.list_all(), ())

    def test_at_threshold_proposes_a_candidate_never_approved(self):
        loop, sessions, audit, skills = _setup(min_occurrences=3)
        for i in range(3):
            _completed_task_with_delegation(sessions, audit, f"t{i}", "finance-agent")

        suggestions = loop.extract_candidate_skills()

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].occurrence_count, 3)
        self.assertEqual(suggestions[0].skill.status, SKILL_CANDIDATE)
        self.assertEqual(skills.list_approved(), ())  # LearningLoop never self-approves

    def test_only_completed_delegation_steps_count(self):
        loop, sessions, audit, skills = _setup(min_occurrences=1)
        plan = Plan(id="plan-t1", task_id="t1", steps=(PlanStep(id="s1", required_capability="finance-agent", input="x"),))
        task = LaylaTask(input="x", id="t1", state=COMPLETED, plan=plan, plan_id=plan.id)
        sessions.save(task)
        audit.record("layla.delegation.failed", {"step_id": "s1"}, task_id="t1")  # never completed

        self.assertEqual(loop.extract_candidate_skills(), ())

    def test_rerunning_does_not_duplicate_an_active_candidate(self):
        loop, sessions, audit, skills = _setup(min_occurrences=2)
        for i in range(2):
            _completed_task_with_delegation(sessions, audit, f"t{i}", "finance-agent")

        first = loop.extract_candidate_skills()
        second = loop.extract_candidate_skills()

        self.assertEqual(len(first), 1)
        self.assertEqual(second, ())  # already has an active candidate for this capability
        self.assertEqual(len(skills.list_all()), 1)

    def test_a_retired_skill_can_be_re_proposed(self):
        loop, sessions, audit, skills = _setup(min_occurrences=2)
        for i in range(2):
            _completed_task_with_delegation(sessions, audit, f"t{i}", "finance-agent")
        first = loop.extract_candidate_skills()
        skills.retire(first[0].skill.id)

        second = loop.extract_candidate_skills()

        self.assertEqual(len(second), 1)


if __name__ == "__main__":
    unittest.main()
