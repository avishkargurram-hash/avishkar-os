import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy, PersonalModel
from avishkar_layla.audit import AuditLogger
from avishkar_layla.business_intelligence import BusinessIntelligenceEngine
from avishkar_layla.executive_dashboard import ExecutiveDashboard
from avishkar_layla.life_os import LifeOS
from avishkar_layla.personal_model import CATEGORY_COMMUNICATION_STYLE
from avishkar_layla.prediction import PredictionEngine
from avishkar_layla.session import SessionManager
from avishkar_layla.skills import SkillRegistry


class TestExecutiveDashboardEmpty(unittest.TestCase):
    def test_no_components_wired_is_honest(self):
        dashboard = ExecutiveDashboard()
        self.assertIn("No Foundation-tier components", dashboard.brief())


class TestExecutiveDashboardWithComponents(unittest.TestCase):
    def test_brief_aggregates_every_wired_component(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        personal_model = PersonalModel(memory)
        personal_model.set(CATEGORY_COMMUNICATION_STYLE, "tone", "direct")
        life_os = LifeOS(personal_model)
        life_os.add_appointment("a1", "board meeting", when="2099-01-01T00:00:00+00:00")
        sessions = SessionManager(memory)
        audit = AuditLogger(memory)
        prediction = PredictionEngine(sessions, audit)
        skills = SkillRegistry(memory)
        bi = BusinessIntelligenceEngine(sessions, audit)

        dashboard = ExecutiveDashboard(
            personal_model=personal_model, life_os=life_os, prediction_engine=prediction,
            skill_registry=skills, business_intelligence=bi,
        )

        brief = dashboard.brief()

        self.assertIn("## Personal Model", brief)
        self.assertIn("## Life OS", brief)
        self.assertIn("board meeting", brief)
        self.assertIn("## Predictions", brief)
        self.assertIn("## Skills", brief)
        self.assertIn("## Business Intelligence", brief)

    def test_only_wired_components_appear(self):
        memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
        dashboard = ExecutiveDashboard(personal_model=PersonalModel(memory))

        brief = dashboard.brief()

        self.assertIn("## Personal Model", brief)
        self.assertNotIn("## Life OS", brief)
        self.assertNotIn("## Skills", brief)


if __name__ == "__main__":
    unittest.main()
