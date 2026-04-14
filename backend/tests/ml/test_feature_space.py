import unittest

from app.ml.prefix_cf import FeatureSpace


class FeatureSpaceTests(unittest.TestCase):
    def test_build_and_vectorize_multi_category(self):
        products = [
            {
                "category": "fountain_pens",
                "vendor": "Lamy",
                "product_type": "Fountain Pens",
                "tags": ["starter"],
                "options": {"Nib Size": ["Fine"]},
                "price_min": 25.0,
                "price_max": 30.0,
            },
            {
                "category": "movies",
                "vendor": "Warner Bros",
                "primary_country": "US",
                "original_language": "en",
                "genres": ["Action"],
                "keywords": ["hero"],
                "production_companies": ["DC Films"],
                "directors": ["Patty Jenkins"],
                "release_year": 2017,
                "runtime_minutes": 141,
                "vote_average": 7.4,
                "popularity": 85.1,
            },
        ]
        fs = FeatureSpace.build(products)
        self.assertGreater(len(fs.feature_index), 0)
        self.assertIn("cat::fountain_pens::num::price_min_z", fs.numeric_stats)
        self.assertIn("cat::movies::num::release_year_z", fs.numeric_stats)

        v_pen = fs.vectorize(products[0])
        v_movie = fs.vectorize(products[1])
        self.assertEqual(len(v_pen), len(fs.feature_index))
        self.assertEqual(len(v_movie), len(fs.feature_index))
        self.assertGreater(v_pen.sum(), 0.0)
        self.assertGreater(v_movie.sum(), 0.0)


if __name__ == "__main__":
    unittest.main()
