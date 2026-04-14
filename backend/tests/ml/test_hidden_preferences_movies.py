import unittest

from app.ml.prefix_cf import FeatureSpace, PrefixCFModel


class HiddenPreferencesMovieTests(unittest.TestCase):
    def test_hidden_preferences_and_gems_for_movies(self):
        movies = [
            {
                "_id": "m1",
                "category": "movies",
                "vendor": "A24",
                "original_language": "en",
                "genres": ["Drama"],
                "directors": ["Greta Gerwig"],
                "release_year": 2019,
                "runtime_minutes": 135,
                "vote_average": 8.0,
                "popularity": 70.0,
            },
            {
                "_id": "m2",
                "category": "movies",
                "vendor": "A24",
                "original_language": "en",
                "genres": ["Drama"],
                "directors": ["Noah Baumbach"],
                "release_year": 2019,
                "runtime_minutes": 136,
                "vote_average": 8.1,
                "popularity": 71.0,
            },
            {
                "_id": "m3",
                "category": "movies",
                "vendor": "Warner Bros",
                "original_language": "en",
                "genres": ["Sci-Fi"],
                "directors": ["Christopher Nolan"],
                "release_year": 2014,
                "runtime_minutes": 169,
                "vote_average": 8.6,
                "popularity": 95.0,
            },
        ]
        fs = FeatureSpace.build(movies)
        model = PrefixCFModel(fs)
        state = model.init_state()

        # Simulate learned preference for a feature the selected set did not contain.
        hidden_key = "cat::movies::multi::directors::christopher nolan"
        hidden_idx = fs.feature_index[hidden_key]
        user_vec = state["user_vec"]
        user_vec[hidden_idx] = 1.0
        state["user_vec"] = user_vec
        state["count"] = 3

        selected = [movies[0], movies[1]]
        hidden = model.detect_hidden_preferences(state, selected, top_n=6)
        self.assertTrue(any(row["feature"] == hidden_key for row in hidden))

        gems = model.get_hidden_gem_products(state, selected, movies, top_n=3)
        self.assertGreater(len(gems), 0)
        top = gems[0][1]
        self.assertEqual(top["_id"], "m3")


if __name__ == "__main__":
    unittest.main()
