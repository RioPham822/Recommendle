import unittest

from fastapi import HTTPException

from app.main import list_products
from scripts.ingest_games_igdb import _build_game_doc
from scripts.ingest_movies_tmdb import _build_movie_doc


class ProductApiConsistencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_price_filters_require_fountain_pen_category(self):
        with self.assertRaises(HTTPException) as exc_info:
            await list_products(category="movies", price_min=10.0, db=None)

        self.assertEqual(exc_info.exception.status_code, 400)
        self.assertIn("fountain_pens", str(exc_info.exception.detail))

    async def test_price_filters_require_explicit_fountain_pen_category(self):
        with self.assertRaises(HTTPException) as exc_info:
            await list_products(price_max=25.0, db=None)

        self.assertEqual(exc_info.exception.status_code, 400)
        self.assertIn("fountain_pens", str(exc_info.exception.detail))


class IngestDocumentConsistencyTests(unittest.TestCase):
    def test_movie_ingest_doc_excludes_pen_only_fields(self):
        movie = {
            "id": 1,
            "title": "Arrival",
            "release_date": "2016-11-11",
            "runtime": 116,
            "vote_average": 7.9,
            "vote_count": 10000,
            "popularity": 90.0,
            "status": "Released",
            "original_language": "en",
            "genres": [{"name": "Science Fiction"}],
            "production_companies": [{"name": "Paramount"}],
            "production_countries": [{"iso_3166_1": "US"}],
            "credits": {"crew": [{"job": "Director", "name": "Denis Villeneuve"}]},
            "keywords": {"keywords": [{"name": "alien"}]},
            "release_dates": {"results": [{"iso_3166_1": "US", "release_dates": [{"certification": "PG-13"}]}]},
        }

        doc = _build_movie_doc(movie)

        for field in ("product_type", "price_min", "price_max", "currency", "tags", "options"):
            self.assertNotIn(field, doc)
        self.assertEqual(doc["runtime_minutes"], 116)
        self.assertEqual(doc["certification"], "PG-13")

    def test_game_ingest_doc_excludes_pen_only_fields(self):
        game = {
            "id": 1,
            "name": "Celeste",
            "first_release_date": 1517529600,
            "total_rating": 88.5,
            "total_rating_count": 500,
            "game_status": 0,
            "hypes": 120,
            "genres": [{"name": "Platform"}],
            "themes": [{"name": "Drama"}],
            "game_modes": [{"name": "Single player"}],
            "player_perspectives": [{"name": "Side view"}],
            "keywords": [{"name": "mountain"}],
            "platforms": [{"name": "PC"}],
            "involved_companies": [{"developer": True, "company": {"name": "Matt Makes Games"}}],
            "summary": "Climb a mountain.",
            "slug": "celeste",
        }

        doc = _build_game_doc(game)

        for field in ("product_type", "price_min", "price_max", "currency", "tags", "options"):
            self.assertNotIn(field, doc)
        self.assertEqual(doc["platforms"], ["PC"])
        self.assertEqual(doc["vendor"], "Matt Makes Games")


if __name__ == "__main__":
    unittest.main()
