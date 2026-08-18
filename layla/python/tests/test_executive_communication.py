import datetime
import unittest

from avishkar_agent import InMemoryMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.audit import AuditLogger
from avishkar_layla.executive_communication import (
    RelationshipContact,
    StaleRelationshipEvaluator,
    record_contact_outcome,
)
from avishkar_layla.notifications import NotificationManager
from avishkar_layla.personal_model import PersonalModel
from avishkar_layla.proactive import ACTION_SUGGEST, ProactiveEngine
from avishkar_layla.session import SessionManager


def _personal_model():
    memory = LaylaMemoryPolicy(InMemoryMemoryPolicy())
    return PersonalModel(memory), memory


def _add_contact(personal_model, contact_id, *, days_ago, name="Alice", do_not_disturb=False):
    last_contact = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago)).isoformat()
    contact = RelationshipContact(
        name=name, channel="email", channel_address=f"{contact_id}@example.com",
        last_contact_date=last_contact, do_not_disturb=do_not_disturb,
    )
    personal_model.set("relationships", contact_id, contact.as_dict(), confirmed=True)
    return last_contact


class TestStaleRelationshipEvaluator(unittest.TestCase):
    def test_stale_contact_produces_a_real_suggest_trigger(self):
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "alice", days_ago=10)
        evaluator = StaleRelationshipEvaluator(personal_model, threshold_days=7)

        triggers = evaluator(engine=None)

        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].action_level, ACTION_SUGGEST)
        self.assertIn("Alice", triggers[0].description)
        self.assertEqual(triggers[0].evidence["contact_id"], "alice")
        self.assertGreaterEqual(triggers[0].evidence["days_since"], 10.0)

    def test_recently_contacted_contact_produces_no_trigger(self):
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "bob", days_ago=1)
        evaluator = StaleRelationshipEvaluator(personal_model, threshold_days=7)

        self.assertEqual(evaluator(engine=None), [])

    def test_do_not_disturb_contact_is_never_suggested(self):
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "carol", days_ago=30, do_not_disturb=True)
        evaluator = StaleRelationshipEvaluator(personal_model, threshold_days=7)

        self.assertEqual(evaluator(engine=None), [])

    def test_custom_eligibility_filter_is_honored(self):
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "dave", days_ago=10)
        evaluator = StaleRelationshipEvaluator(
            personal_model, threshold_days=7, is_eligible=lambda contact_id, value: False,
        )
        self.assertEqual(evaluator(engine=None), [])

    def test_the_same_staleness_state_is_never_suggested_twice(self):
        """Real retry-storm prevention -- matching
        EnvironmentalChangeEvaluator's (Part VI) dedup discipline.
        """
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "erin", days_ago=10)
        evaluator = StaleRelationshipEvaluator(personal_model, threshold_days=7)

        first = evaluator(engine=None)
        second = evaluator(engine=None)

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_a_new_contact_outcome_makes_it_eligible_for_a_future_suggestion(self):
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "frank", days_ago=10)
        evaluator = StaleRelationshipEvaluator(personal_model, threshold_days=7)
        evaluator(engine=None)  # first suggestion

        record_contact_outcome(personal_model, "frank", channel="email", message_id="msg-1")
        self.assertEqual(evaluator(engine=None), [])  # freshly contacted -- no longer stale

    def test_multiple_stale_contacts_all_produce_triggers(self):
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "grace", days_ago=8, name="Grace")
        _add_contact(personal_model, "henry", days_ago=15, name="Henry")
        evaluator = StaleRelationshipEvaluator(personal_model, threshold_days=7)

        triggers = evaluator(engine=None)
        self.assertEqual(len(triggers), 2)


class TestRecordContactOutcome(unittest.TestCase):
    def test_updates_last_contact_fields_for_real(self):
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "ivy", days_ago=10)

        record_contact_outcome(personal_model, "ivy", channel="whatsapp", message_id="wamid-42")

        fact = personal_model.get("relationships", "ivy")
        self.assertEqual(fact.value["last_contact_channel"], "whatsapp")
        self.assertEqual(fact.value["last_contact_message_id"], "wamid-42")

    def test_unknown_contact_raises(self):
        personal_model, _ = _personal_model()
        with self.assertRaises(ValueError):
            record_contact_outcome(personal_model, "nobody", channel="email", message_id="m1")

    def test_outcome_is_a_real_correction_not_a_silent_overwrite(self):
        """PersonalModel.correct() marks the fact as corrected --
        provenance-tracked, matching CONTRACT.md SS19's real-
        contradiction-handling discipline.
        """
        personal_model, _ = _personal_model()
        _add_contact(personal_model, "jack", days_ago=10)
        record_contact_outcome(personal_model, "jack", channel="slack", message_id="1620000000.0001")

        fact = personal_model.get("relationships", "jack")
        self.assertTrue(fact.corrected)


class TestStaleRelationshipEndToEndWithProactiveEngine(unittest.TestCase):
    def test_full_chain_from_personal_model_to_a_real_proactive_trigger(self):
        personal_model, memory = _personal_model()
        _add_contact(personal_model, "kate", days_ago=14, name="Kate")

        sessions = SessionManager(memory)
        audit = AuditLogger(memory)
        notifications = NotificationManager()
        evaluator = StaleRelationshipEvaluator(personal_model, threshold_days=7)
        engine = ProactiveEngine(sessions, audit, notifications, extra_evaluators=(evaluator,))

        triggers = engine.evaluate()

        self.assertEqual(len(triggers), 1)
        self.assertIn("Kate", triggers[0].description)
        # ACTION_SUGGEST -> a real Notification, never an autonomous send.
        pending = notifications.pending()
        self.assertEqual(len(pending), 1)
        self.assertIn("Kate", pending[0].message)


if __name__ == "__main__":
    unittest.main()
