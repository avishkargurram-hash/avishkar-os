import unittest

from avishkar_layla import LaylaTask
from avishkar_layla.capability_resolver import CapabilityResolver
from avishkar_layla.errors import UnknownCapabilityError
from avishkar_layla.planning import Planner


class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.resolver = CapabilityResolver({
            "software-ai-engineering": "Software & AI Engineering",
            "legal-compliance": "Legal & Compliance",
            "finance-economics": "Finance & Economics",
        })
        self.planner = Planner(self.resolver)

    def test_infers_multiple_relevant_capabilities(self):
        task = LaylaTask(input="Build the backend software for our new product, and get a legal compliance review of data handling.")
        plan = self.planner.plan(task)

        capabilities = {step.required_capability for step in plan.steps}
        self.assertIn("software-ai-engineering", capabilities)
        self.assertIn("legal-compliance", capabilities)
        self.assertNotIn("finance-economics", capabilities)

    def test_explicit_requested_capabilities_take_precedence(self):
        task = LaylaTask(input="anything")
        plan = self.planner.plan(task, requested_capabilities=["finance-economics"])
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].required_capability, "finance-economics")

    def test_no_inferable_capability_raises(self):
        task = LaylaTask(input="something with no domain keywords at all")
        with self.assertRaises(UnknownCapabilityError):
            self.planner.plan(task)

    def test_plan_steps_carry_risk_level_from_task_input(self):
        task = LaylaTask(input="Please deploy to production the new software release")
        plan = self.planner.plan(task)
        self.assertTrue(all(step.risk_level == "HIGH" for step in plan.steps))

    def test_plan_is_linked_to_task(self):
        task = LaylaTask(input="review the legal contract")
        plan = self.planner.plan(task)
        self.assertEqual(plan.task_id, task.id)


if __name__ == "__main__":
    unittest.main()
