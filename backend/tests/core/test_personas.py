import unittest

from app import personas


class PersonasTests(unittest.TestCase):
    def test_list_personas_returns_copies(self):
        listed = personas.list_personas()

        self.assertEqual(len(listed), len(personas.PERSONAS))
        listed[0]["display_name"] = "Changed"
        self.assertNotEqual(listed[0]["display_name"], personas.PERSONAS[0]["display_name"])

    def test_get_persona_returns_copy_for_known_id(self):
        persona = personas.get_persona("action-thriller-mainstream")

        self.assertEqual(persona["category"], "movies")
        persona["display_name"] = "Modified"
        self.assertNotEqual(persona["display_name"], personas.PERSONAS[0]["display_name"])

    def test_get_persona_raises_for_unknown_id(self):
        with self.assertRaises(KeyError):
            personas.get_persona("missing-persona")


if __name__ == "__main__":
    unittest.main()
