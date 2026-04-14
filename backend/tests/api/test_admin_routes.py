import csv
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.db import ProductRecord
from app.routes import admin
from app.routes.admin import (
    MLConfigUpdateRequest,
    _allowed_product_fields,
    _build_product_filters,
    _extract_image_url,
    _parse_filters,
    _product_row,
    _split_list_value,
    clear_user_progress,
    delete_user_account,
    export_products,
    get_admin_me,
    list_admin_categories,
    list_admin_products,
    list_users,
    update_ml_config,
)


class _ScalarResult:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return _ScalarResult(self._values)


class _FakeDB:
    def __init__(self, scalar_values=None, execute_values=None):
        self.scalar_values = list(scalar_values or [])
        self.execute_values = list(execute_values or [])
        self.commit_calls = 0
        self.execute_calls = 0

    async def scalar(self, _stmt):
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return None

    async def execute(self, _stmt):
        self.execute_calls += 1
        if self.execute_values:
            return _ExecuteResult(self.execute_values.pop(0))
        return _ExecuteResult([])

    async def commit(self):
        self.commit_calls += 1


class AdminRouteFieldTests(unittest.TestCase):
    def test_movies_exclude_fountain_pen_only_fields(self):
        allowed = _allowed_product_fields("movies")

        self.assertNotIn("price_min", allowed)
        self.assertNotIn("price_max", allowed)
        self.assertNotIn("currency", allowed)
        self.assertNotIn("nib_sizes", allowed)
        self.assertIn("release_year", allowed)
        self.assertIn("runtime_minutes", allowed)
        self.assertIn("vote_average", allowed)

    def test_games_exclude_fountain_pen_only_fields(self):
        allowed = _allowed_product_fields("games")

        self.assertNotIn("price_min", allowed)
        self.assertNotIn("price_max", allowed)
        self.assertNotIn("currency", allowed)
        self.assertNotIn("nib_sizes", allowed)
        self.assertIn("platforms", allowed)
        self.assertIn("total_rating", allowed)

    def test_fountain_pens_keep_price_fields(self):
        allowed = _allowed_product_fields("fountain_pens")

        self.assertIn("price_min", allowed)
        self.assertIn("price_max", allowed)
        self.assertIn("currency", allowed)
        self.assertIn("product_type", allowed)

    def test_split_list_value_supports_lists_pipes_commas_and_blank_values(self):
        self.assertEqual(_split_list_value(None), [])
        self.assertEqual(_split_list_value(["  a ", "", "b"]), ["a", "b"])
        self.assertEqual(_split_list_value("alpha| beta "), ["alpha", "beta"])
        self.assertEqual(_split_list_value("red, blue"), ["red", "blue"])
        self.assertEqual(_split_list_value(""), [])
        self.assertEqual(_split_list_value("single value"), ["single value"])

    def test_extract_image_url_supports_string_dict_and_list(self):
        self.assertEqual(_extract_image_url(" https://example.com/a.png "), "https://example.com/a.png")
        self.assertEqual(_extract_image_url({"src": "https://example.com/b.png"}), "https://example.com/b.png")
        self.assertEqual(
            _extract_image_url([{"url": ""}, {"url": "https://example.com/c.png"}]),
            "https://example.com/c.png",
        )
        self.assertIsNone(_extract_image_url({"missing": "url"}))

    def test_parse_filters_accepts_empty_and_object_json(self):
        self.assertEqual(_parse_filters(None), {})
        self.assertEqual(_parse_filters(""), {})
        self.assertEqual(_parse_filters('{"genre":"rpg"}'), {"genre": "rpg"})

    def test_parse_filters_rejects_invalid_json_and_non_object_values(self):
        with self.assertRaises(HTTPException) as invalid_json:
            _parse_filters("{")
        self.assertEqual(invalid_json.exception.status_code, 400)

        with self.assertRaises(HTTPException) as invalid_shape:
            _parse_filters('["rpg"]')
        self.assertEqual(invalid_shape.exception.status_code, 400)

    def test_build_product_filters_rejects_invalid_numeric_value(self):
        with self.assertRaises(HTTPException) as exc:
            _build_product_filters("fountain_pens", None, {"price_min": "cheap"})
        self.assertEqual(exc.exception.status_code, 400)
        self.assertIn("Invalid numeric filter", exc.exception.detail)

    def test_product_row_maps_image_and_chip_columns(self):
        record = ProductRecord(
            id="prod-1",
            category="games",
            data={
                "title": "Chronicles",
                "genres": "RPG|Adventure",
                "images": [{"url": "https://example.com/game.png"}],
                "description": {"unexpected": "dict"},
            },
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        columns = [
            {"key": "title", "kind": "title"},
            {"key": "genres", "kind": "chips"},
            {"key": "description", "kind": "long_text"},
        ]

        row = _product_row(record, columns)

        self.assertEqual(row["id"], "prod-1")
        self.assertEqual(row["thumbnail"], "https://example.com/game.png")
        self.assertEqual(row["genres"], ["RPG", "Adventure"])
        self.assertIsNone(row["description"])


class AdminRouteEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_admin_me_returns_minimal_admin_profile(self):
        admin_user = SimpleNamespace(id="admin-1", username="root", role="admin", display_name="Root")

        result = await get_admin_me(admin_user)

        self.assertEqual(
            result,
            {
                "id": "admin-1",
                "username": "root",
                "role": "admin",
                "display_name": "Root",
            },
        )

    async def test_list_users_maps_service_records_to_response_model(self):
        created = datetime(2026, 1, 1, 12, 0, 0)
        users = [
            {
                "_id": "u1",
                "username": "alice",
                "display_name": "Alice",
                "created_at": created,
                "updated_at": created,
                "active_sessions": 2,
            }
        ]
        with patch.object(admin.auth_service, "list_users", AsyncMock(return_value=users)) as mocked:
            result = await list_users(db=object(), _=SimpleNamespace(role="admin"))

        mocked.assert_awaited_once()
        self.assertEqual(result[0].id, "u1")
        self.assertEqual(result[0].username, "alice")
        self.assertEqual(result[0].active_sessions, 2)

    async def test_delete_user_account_rejects_missing_user(self):
        db = _FakeDB(scalar_values=[None])

        with self.assertRaises(HTTPException) as exc:
            await delete_user_account("missing", db=db, _=SimpleNamespace(role="admin"))

        self.assertEqual(exc.exception.status_code, 404)

    async def test_delete_user_account_removes_games_and_invalidates_ratings(self):
        user = SimpleNamespace(id="user-1", username="alice", display_name="Alice")
        db = _FakeDB(scalar_values=[user], execute_values=[["game-1", "game-2"]])

        with patch.object(admin.recommender, "invalidate_ratings") as invalidate:
            result = await delete_user_account("user-1", db=db, _=SimpleNamespace(role="admin"))

        self.assertEqual(result, {"success": True, "deleted_game_count": 2})
        self.assertEqual(db.commit_calls, 1)
        self.assertGreaterEqual(db.execute_calls, 4)
        invalidate.assert_called_once()

    async def test_clear_user_progress_rejects_missing_user(self):
        db = _FakeDB(scalar_values=[None])

        with self.assertRaises(HTTPException) as exc:
            await clear_user_progress("missing", db=db, _=SimpleNamespace(role="admin"))

        self.assertEqual(exc.exception.status_code, 404)

    async def test_clear_user_progress_removes_games_but_not_user(self):
        user = SimpleNamespace(id="user-1", username="alice", display_name="Alice")
        db = _FakeDB(scalar_values=[user], execute_values=[["game-1"]])

        with patch.object(admin.recommender, "invalidate_ratings") as invalidate:
            result = await clear_user_progress("user-1", db=db, _=SimpleNamespace(role="admin"))

        self.assertEqual(result, {"success": True, "cleared_game_count": 1})
        self.assertEqual(db.commit_calls, 1)
        self.assertGreaterEqual(db.execute_calls, 4)
        invalidate.assert_called_once()

    async def test_update_ml_config_returns_service_values(self):
        payload = MLConfigUpdateRequest(values={"learning_rate": 0.3})
        with patch.object(
            admin.ml_config_service,
            "update",
            AsyncMock(return_value={"learning_rate": 0.3}),
        ) as mocked:
            result = await update_ml_config(payload, db=object(), _=SimpleNamespace(role="admin"))

        mocked.assert_awaited_once()
        self.assertEqual(result["values"], {"learning_rate": 0.3})
        self.assertIn("defaults", result)

    async def test_update_ml_config_translates_value_errors(self):
        payload = MLConfigUpdateRequest(values={"learning_rate": -1})
        with patch.object(
            admin.ml_config_service,
            "update",
            AsyncMock(side_effect=ValueError("bad config")),
        ):
            with self.assertRaises(HTTPException) as exc:
                await update_ml_config(payload, db=object(), _=SimpleNamespace(role="admin"))

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "bad config")

    async def test_list_admin_products_returns_columns_and_rows(self):
        product = ProductRecord(
            id="movie-1",
            category="movies",
            data={
                "title": "Arrival",
                "vendor": "Paramount",
                "genres": ["Sci-Fi"],
                "images": [{"url": "https://example.com/arrival.png"}],
            },
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        db = _FakeDB(
            scalar_values=[1],
            execute_values=[
                [product],
                [product.data],
            ],
        )

        result = await list_admin_products(
            category="movies",
            search="Arrival",
            filters='{"vendor":"Paramount"}',
            limit=25,
            offset=0,
            sort_field="title",
            sort_dir="asc",
            db=db,
            _=SimpleNamespace(role="admin"),
        )

        self.assertEqual(result.category, "movies")
        self.assertEqual(result.total, 1)
        self.assertEqual(result.rows[0]["title"], "Arrival")
        self.assertEqual(result.rows[0]["genres"], ["Sci-Fi"])
        self.assertEqual(result.rows[0]["image_url"], "https://example.com/arrival.png")

    async def test_list_admin_products_rejects_bad_category_and_bad_filters(self):
        db = _FakeDB()

        with self.assertRaises(HTTPException) as bad_category:
            await list_admin_products(
                category="unknown",
                db=db,
                _=SimpleNamespace(role="admin"),
            )
        self.assertEqual(bad_category.exception.status_code, 400)

        with self.assertRaises(HTTPException) as bad_filters:
            await list_admin_products(
                category="movies",
                filters="{",
                db=db,
                _=SimpleNamespace(role="admin"),
            )
        self.assertEqual(bad_filters.exception.status_code, 400)

    async def test_export_products_streams_csv_rows(self):
        product = ProductRecord(
            id="pen-1",
            category="fountain_pens",
            data={
                "title": "Pilot Custom 74",
                "vendor": "Pilot",
                "nib_sizes": ["F", "M"],
                "images": "https://example.com/pen.png",
            },
            created_at=datetime(2026, 1, 1, 12, 0, 0),
        )
        db = _FakeDB(
            execute_values=[
                [product.data],
                [product],
                [],
            ],
        )

        response = await export_products(
            category="fountain_pens",
            db=db,
            _=SimpleNamespace(role="admin"),
        )

        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)
        rows = list(csv.reader("".join(chunks).splitlines()))

        self.assertEqual(response.media_type, "text/csv")
        self.assertEqual(rows[0][0], "thumbnail")
        self.assertIn("title", rows[0])
        self.assertIn("Pilot Custom 74", rows[1])
        self.assertIn("F | M", rows[1])

    async def test_export_products_rejects_invalid_category(self):
        with self.assertRaises(HTTPException) as exc:
            await export_products(category="not-real", db=_FakeDB(), _=SimpleNamespace(role="admin"))

        self.assertEqual(exc.exception.status_code, 400)

    async def test_list_admin_categories_returns_supported_categories(self):
        result = await list_admin_categories(_=SimpleNamespace(role="admin"))

        category_ids = {item["id"] for item in result}
        self.assertTrue({"movies", "games", "fountain_pens"}.issubset(category_ids))


if __name__ == "__main__":
    unittest.main()
