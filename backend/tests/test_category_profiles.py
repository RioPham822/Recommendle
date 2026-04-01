import unittest

from app.category_profiles import (
    extract_feature_tokens,
    get_category_profile,
    humanize_feature,
    normalize_category,
    supported_categories,
)


class CategoryProfileTests(unittest.TestCase):
    def test_pen_feature_extraction(self):
        pen = {
            "category": "fountain_pens",
            "vendor": "TWSBI",
            "product_type": "Fountain Pens",
            "tags": ["demonstrator", "piston-fill"],
            "options": {"Nib Size": ["Fine", "Medium"]},
            "price_min": 35.0,
            "price_max": 39.0,
        }
        tokens, nums = extract_feature_tokens(pen, "fountain_pens")
        self.assertIn("cat::fountain_pens::cat::vendor::twsbi", tokens)
        self.assertIn("cat::fountain_pens::multi::tags::demonstrator", tokens)
        self.assertIn("cat::fountain_pens::multi::option::nib size|fine", tokens)
        self.assertIn("cat::fountain_pens::num::price_min_z", nums)
        self.assertIn("cat::fountain_pens::num::price_max_z", nums)

    def test_movie_feature_extraction(self):
        movie = {
            "category": "movies",
            "vendor": "Warner Bros.",
            "primary_country": "US",
            "original_language": "en",
            "certification": "PG-13",
            "decade_bucket": "2010s",
            "runtime_bucket": "long",
            "genres": ["Science Fiction", "Drama"],
            "keywords": ["time travel"],
            "production_companies": ["Syncopy"],
            "directors": ["Christopher Nolan"],
            "release_year": 2014,
            "runtime_minutes": 169,
            "vote_average": 8.4,
            "popularity": 90.3,
        }
        tokens, nums = extract_feature_tokens(movie, "movies")
        self.assertIn("cat::movies::cat::original_language::en", tokens)
        self.assertIn("cat::movies::multi::genres::science fiction", tokens)
        self.assertIn("cat::movies::multi::directors::christopher nolan", tokens)
        self.assertIn("cat::movies::num::release_year_z", nums)
        self.assertIn("cat::movies::num::runtime_minutes_z", nums)
        self.assertIn("cat::movies::num::vote_average_z", nums)
        self.assertIn("cat::movies::num::popularity_z", nums)

    def test_humanize_feature(self):
        label = humanize_feature("cat::movies::multi::directors::christopher nolan")
        self.assertEqual(label, "Christopher Nolan")

    def test_normalize_category_default(self):
        self.assertEqual(normalize_category(None), "fountain_pens")

    def test_all_supported_categories_use_100_item_onboarding_pool(self):
        for category in supported_categories():
            profile = get_category_profile(category)
            self.assertEqual(profile.onboarding_pool_size, 100)


if __name__ == "__main__":
    unittest.main()
