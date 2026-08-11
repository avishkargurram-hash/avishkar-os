import tempfile
import unittest
from pathlib import Path

from avishkar_agent import InMemoryMemoryPolicy
from avishkar_memory import FileMemoryPolicy

from avishkar_layla import LaylaMemoryPolicy
from avishkar_layla.personal_model import (
    CATEGORY_COMMUNICATION_STYLE,
    CATEGORY_GOALS,
    CATEGORY_IDENTITY,
    CATEGORY_PREFERENCES,
    CATEGORY_RELATIONSHIPS,
    PersonalFactContradictionError,
    PersonalModel,
    SensitiveCategoryNotConfirmedError,
)


def _model() -> PersonalModel:
    return PersonalModel(LaylaMemoryPolicy(InMemoryMemoryPolicy()))


class TestPersonalModelBasics(unittest.TestCase):
    def test_set_and_get_round_trips(self):
        model = _model()
        model.set(CATEGORY_PREFERENCES, "preferred_meeting_time", "morning")

        fact = model.get(CATEGORY_PREFERENCES, "preferred_meeting_time")

        self.assertEqual(fact.value, "morning")
        self.assertEqual(fact.category, CATEGORY_PREFERENCES)
        self.assertFalse(fact.corrected)

    def test_get_missing_key_returns_none(self):
        model = _model()
        self.assertIsNone(model.get(CATEGORY_GOALS, "never-set"))

    def test_unknown_category_raises(self):
        model = _model()
        with self.assertRaises(ValueError):
            model.set("not-a-real-category", "key", "value")

    def test_forget_removes_fact_and_index_entry(self):
        model = _model()
        model.set(CATEGORY_IDENTITY, "display_name", "Avishkar")

        model.forget(CATEGORY_IDENTITY, "display_name")

        self.assertIsNone(model.get(CATEGORY_IDENTITY, "display_name"))
        self.assertEqual(model.get_category(CATEGORY_IDENTITY), {})


class TestPersonalModelIdempotencyAndContradiction(unittest.TestCase):
    def test_setting_the_same_value_twice_is_a_no_op(self):
        model = _model()
        first = model.set(CATEGORY_PREFERENCES, "tone", "direct")
        second = model.set(CATEGORY_PREFERENCES, "tone", "direct")

        self.assertEqual(first.stored_at, second.stored_at)  # never re-written

    def test_setting_a_different_value_without_resolution_raises(self):
        model = _model()
        model.set(CATEGORY_PREFERENCES, "tone", "direct")

        with self.assertRaises(PersonalFactContradictionError):
            model.set(CATEGORY_PREFERENCES, "tone", "diplomatic")

    def test_resolve_ignore_keeps_the_existing_value(self):
        model = _model()
        model.set(CATEGORY_PREFERENCES, "tone", "direct")

        result = model.set(CATEGORY_PREFERENCES, "tone", "diplomatic", resolve="ignore")

        self.assertEqual(result.value, "direct")
        self.assertEqual(model.get(CATEGORY_PREFERENCES, "tone").value, "direct")

    def test_resolve_overwrite_replaces_the_value(self):
        model = _model()
        model.set(CATEGORY_PREFERENCES, "tone", "direct")

        model.set(CATEGORY_PREFERENCES, "tone", "diplomatic", resolve="overwrite")

        self.assertEqual(model.get(CATEGORY_PREFERENCES, "tone").value, "diplomatic")

    def test_correct_always_succeeds_and_marks_corrected(self):
        model = _model()
        model.set(CATEGORY_PREFERENCES, "tone", "direct")

        fact = model.correct(CATEGORY_PREFERENCES, "tone", "diplomatic", reason="user explicitly asked to soften tone")

        self.assertEqual(fact.value, "diplomatic")
        self.assertTrue(fact.corrected)
        self.assertTrue(model.get(CATEGORY_PREFERENCES, "tone").corrected)


class TestPersonalModelSensitiveCategories(unittest.TestCase):
    def test_relationships_write_without_confirmation_raises(self):
        model = _model()
        with self.assertRaises(SensitiveCategoryNotConfirmedError):
            model.set(CATEGORY_RELATIONSHIPS, "person-1", {"role": "colleague"})

    def test_relationships_write_with_confirmation_succeeds(self):
        model = _model()
        model.set(CATEGORY_RELATIONSHIPS, "person-1", {"role": "colleague"}, confirmed=True)

        self.assertEqual(model.get(CATEGORY_RELATIONSHIPS, "person-1").value, {"role": "colleague"})

    def test_correct_on_sensitive_category_also_requires_confirmation(self):
        model = _model()
        model.set(CATEGORY_RELATIONSHIPS, "person-1", {"role": "colleague"}, confirmed=True)

        with self.assertRaises(SensitiveCategoryNotConfirmedError):
            model.correct(CATEGORY_RELATIONSHIPS, "person-1", {"role": "manager"}, reason="promoted")


class TestPersonalModelCategoryListingAndSummary(unittest.TestCase):
    def test_get_category_returns_every_fact(self):
        model = _model()
        model.set(CATEGORY_GOALS, "q3-goal", "ship Layla foundation")
        model.set(CATEGORY_GOALS, "q4-goal", "expand perception layer")

        facts = model.get_category(CATEGORY_GOALS)

        self.assertEqual(set(facts.keys()), {"q3-goal", "q4-goal"})

    def test_summary_includes_non_sensitive_values_but_redacts_sensitive_ones(self):
        model = _model()
        model.set(CATEGORY_COMMUNICATION_STYLE, "tone", "direct")
        model.set(CATEGORY_RELATIONSHIPS, "person-1", {"role": "colleague"}, confirmed=True)

        summary = model.summary()

        self.assertIn("tone=", summary)
        self.assertIn("sensitive, not summarized", summary)
        self.assertNotIn("colleague", summary)

    def test_summary_with_no_data_is_honest(self):
        model = _model()
        self.assertIn("No personal model data recorded yet", model.summary())


class TestPersonalModelCrossInstancePersistence(unittest.TestCase):
    """Same cross-instance persistence proof pattern test_session.py/
    test_delegation_idempotency.py already established -- a fresh
    PersonalModel instance against the same on-disk store sees every
    fact a prior instance wrote.
    """

    def test_facts_survive_a_simulated_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            memory = LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp)))
            first = PersonalModel(memory)
            first.set(CATEGORY_IDENTITY, "role", "Founder")

            second = PersonalModel(LaylaMemoryPolicy(FileMemoryPolicy(Path(tmp))))
            fact = second.get(CATEGORY_IDENTITY, "role")

            self.assertIsNotNone(fact)
            self.assertEqual(fact.value, "Founder")


if __name__ == "__main__":
    unittest.main()
