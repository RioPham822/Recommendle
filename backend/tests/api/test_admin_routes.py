import unittest

from app.routes.admin import _allowed_product_fields


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


if __name__ == "__main__":
    unittest.main()
