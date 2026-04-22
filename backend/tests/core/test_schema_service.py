import unittest

from app.services.schema_service import ensure_multicategory_compatibility


class _FakeDB:
    def __init__(self, scalar_value):
        self.scalar_value = scalar_value

    async def scalar(self, _stmt):
        return self.scalar_value


class SchemaServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_multicategory_compatibility_allows_fully_migrated_data(self):
        await ensure_multicategory_compatibility(_FakeDB(0))

    async def test_ensure_multicategory_compatibility_raises_for_missing_categories(self):
        with self.assertRaises(RuntimeError) as exc:
            await ensure_multicategory_compatibility(_FakeDB(3))

        self.assertIn("python -m scripts.load_db", str(exc.exception))
        self.assertIn("missing documents: 3", str(exc.exception))


if __name__ == "__main__":
    unittest.main()
