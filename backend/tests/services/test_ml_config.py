import unittest
from datetime import datetime

from app.services.ml_config import (
    DEFAULT_ML_CONFIG,
    ML_CONFIG_KEY,
    MLConfigService,
    _ml_config_cache,
    get_ml_config,
)


class _FakeConfigRecord:
    def __init__(self, key, value, updated_at=None):
        self.key = key
        self.value = value
        self.updated_at = updated_at or datetime.utcnow()


class _FakeDB:
    def __init__(self, scalar_results=None):
        self.scalar_results = list(scalar_results or [])
        self.added = []
        self.commits = 0

    async def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


class MLConfigTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _ml_config_cache.clear()
        _ml_config_cache.update(DEFAULT_ML_CONFIG)

    def test_get_ml_config_returns_copy(self):
        result = get_ml_config()
        result["selection_weight"] = 999

        self.assertNotEqual(_ml_config_cache["selection_weight"], 999)
        self.assertEqual(
            _ml_config_cache["selection_weight"],
            DEFAULT_ML_CONFIG["selection_weight"],
        )

    async def test_ensure_loaded_creates_default_record_when_missing(self):
        db = _FakeDB([None])

        result = await MLConfigService.ensure_loaded(db)

        self.assertEqual(result, DEFAULT_ML_CONFIG)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].key, ML_CONFIG_KEY)
        self.assertEqual(db.added[0].value, DEFAULT_ML_CONFIG)
        self.assertEqual(db.commits, 1)

    async def test_ensure_loaded_merges_existing_record_values(self):
        record = _FakeConfigRecord(
            ML_CONFIG_KEY,
            {
                "selection_weight": "2.5",
                "negative_weight": 0.9,
            },
        )
        db = _FakeDB([record])

        result = await MLConfigService.ensure_loaded(db)

        self.assertEqual(result["selection_weight"], 2.5)
        self.assertEqual(result["negative_weight"], 0.9)
        self.assertEqual(result["decay"], DEFAULT_ML_CONFIG["decay"])
        self.assertEqual(db.commits, 0)

    async def test_ensure_loaded_ignores_invalid_existing_values(self):
        record = _FakeConfigRecord(
            ML_CONFIG_KEY,
            {
                "selection_weight": "bad-value",
                "decay": None,
                "negative_weight": 0.75,
            },
        )
        db = _FakeDB([record])

        result = await MLConfigService.ensure_loaded(db)

        self.assertEqual(
            result["selection_weight"],
            DEFAULT_ML_CONFIG["selection_weight"],
        )
        self.assertEqual(result["decay"], DEFAULT_ML_CONFIG["decay"])
        self.assertEqual(result["negative_weight"], 0.75)

    async def test_update_changes_only_provided_keys(self):
        record = _FakeConfigRecord(ML_CONFIG_KEY, dict(DEFAULT_ML_CONFIG))
        db = _FakeDB([record, record])

        result = await MLConfigService.update(
            db,
            {
                "selection_weight": "1.8",
                "negative_weight": 0.95,
            },
        )

        self.assertEqual(result["selection_weight"], 1.8)
        self.assertEqual(result["negative_weight"], 0.95)
        self.assertEqual(result["decay"], DEFAULT_ML_CONFIG["decay"])
        self.assertEqual(record.value["selection_weight"], 1.8)
        self.assertEqual(record.value["negative_weight"], 0.95)
        self.assertEqual(db.commits, 1)

    async def test_update_creates_record_if_missing_after_load(self):
        initial_missing = None
        second_lookup_missing = None
        db = _FakeDB([initial_missing, second_lookup_missing])

        result = await MLConfigService.update(
            db,
            {
                "bias_learning_rate": 0.5,
            },
        )

        self.assertEqual(result["bias_learning_rate"], 0.5)
        self.assertEqual(len(db.added), 2)
        self.assertEqual(db.added[0].key, ML_CONFIG_KEY)
        self.assertEqual(db.added[1].key, ML_CONFIG_KEY)
        self.assertEqual(db.commits, 2)

    async def test_update_rejects_invalid_numeric_value(self):
        record = _FakeConfigRecord(ML_CONFIG_KEY, dict(DEFAULT_ML_CONFIG))
        db = _FakeDB([record, record])

        with self.assertRaisesRegex(
            ValueError,
            "Invalid numeric value for 'selection_weight'",
        ):
            await MLConfigService.update(
                db,
                {
                    "selection_weight": "not-a-number",
                },
            )
