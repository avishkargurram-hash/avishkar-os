import unittest

from avishkar_prompt import (
    MissingVariableError,
    PromptVariable,
    PromptVersion,
    UnknownVariableError,
    render,
)


class TestPromptVersionValidation(unittest.TestCase):
    def test_undeclared_template_variable_raises_at_construction(self):
        with self.assertRaises(UnknownVariableError):
            PromptVersion(version="1.0.0", template="Hello {name}", variables=())

    def test_declared_variable_construction_succeeds(self):
        version = PromptVersion(
            version="1.0.0",
            template="Hello {name}",
            variables=(PromptVariable(name="name"),),
        )
        self.assertEqual(version.variable_names, ("name",))

    def test_extra_declared_but_unused_variable_is_fine(self):
        # Declaring a variable the template doesn't use isn't an error --
        # only using an undeclared one is.
        version = PromptVersion(
            version="1.0.0",
            template="Hello there",
            variables=(PromptVariable(name="unused"),),
        )
        self.assertEqual(version.variable_names, ("unused",))


class TestRender(unittest.TestCase):
    def test_renders_with_all_required_variables(self):
        version = PromptVersion(
            version="1.0.0",
            template="Hello {name}, welcome to {product}.",
            variables=(PromptVariable(name="name"), PromptVariable(name="product")),
        )
        text = render(version, {"name": "Ada", "product": "Avishkar OS"})
        self.assertEqual(text, "Hello Ada, welcome to Avishkar OS.")

    def test_missing_required_variable_raises(self):
        version = PromptVersion(
            version="1.0.0",
            template="Hello {name}",
            variables=(PromptVariable(name="name", required=True),),
        )
        with self.assertRaises(MissingVariableError):
            render(version, {})

    def test_optional_variable_can_be_omitted_if_not_used(self):
        version = PromptVersion(
            version="1.0.0",
            template="Static text.",
            variables=(PromptVariable(name="optional_hint", required=False),),
        )
        self.assertEqual(render(version, {}), "Static text.")

    def test_extra_unknown_keys_in_values_are_ignored(self):
        version = PromptVersion(
            version="1.0.0",
            template="Hello {name}",
            variables=(PromptVariable(name="name"),),
        )
        text = render(version, {"name": "Ada", "unrelated_context": "ignored"})
        self.assertEqual(text, "Hello Ada")


if __name__ == "__main__":
    unittest.main()
