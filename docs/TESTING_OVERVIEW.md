# Testing Overview

This document explains what our testing covers and why it matters.

## Why We Test

Recommendle is more than a standard web app. It includes:

- account and session handling
- category-specific product data
- gameplay logic across onboarding and rounds
- an AI recommendation model that learns from user choices
- admin tools for managing products and system settings

Because of that, testing serves two purposes:

1. To make sure the software works correctly
2. To make sure the recommendation model stays useful and does not quietly get worse over time

In simple terms, our tests help answer questions like:

- Can a user register, log in, and play safely?
- Does the game move through onboarding and rounds correctly?
- Does the AI learn from what the player picks?
- Do recommendations remain sensible after code changes?
- Can the system handle incomplete or messy data without failing?

## How The Tests Are Organized

The backend tests are grouped into four areas:

- `api`
  - checks API-facing behavior and category-specific product consistency
- `core`
  - checks shared helpers, category profiles, and basic data utilities
- `services`
  - checks gameplay, auth, recommender service logic, and game summaries
- `ml`
  - checks the recommendation model, model validation, and model robustness

This structure makes it easier to understand what is being tested and why.

Representative test files live under [backend/tests](../backend/tests/).

## How To Run The Backend Tests

Run the backend unit test suite from `backend/`:

```bash
python -m unittest discover -s tests -v
```

Generate coverage while omitting the `tests` directory itself and ingestion-oriented `scripts` modules:

```bash
python -m coverage run --omit="tests/*,scripts/*" -m unittest discover -s tests -v
python -m coverage report --omit="tests/*,scripts/*"
python -m coverage html --omit="tests/*,scripts/*"
```

The HTML report is written to `backend/htmlcov/index.html`.

## What We Test In General

### 1. API and Data Consistency Tests

These tests check that product data is exposed consistently across categories and that category-specific fields are handled correctly.

Examples:

- making sure movie and game records do not accidentally expose fountain-pen-only fields
- making sure category-specific filters behave the right way
- making sure admin-facing field lists match the correct category

Why this matters:

- It protects the user experience
- It prevents confusing or misleading product information
- It reduces the chance of category mix-ups as the project grows

Representative files:

- [test_admin_routes.py](../backend/tests/api/test_admin_routes.py)
- [test_product_api_consistency.py](../backend/tests/api/test_product_api_consistency.py)

### 2. Core Utility Tests

These tests focus on shared building blocks used across the app.

Examples:

- category normalization
- category profile behavior
- helper functions that convert database records into the format expected by the app
- onboarding selection bounds

Why this matters:

- These helpers sit underneath many features
- A small mistake in shared logic can break multiple parts of the system

Representative files:

- [test_category_profiles.py](../backend/tests/core/test_category_profiles.py)
- [test_db_helpers.py](../backend/tests/core/test_db_helpers.py)
- [test_onboarding_selection_bounds.py](../backend/tests/core/test_onboarding_selection_bounds.py)

### 3. Service and Gameplay Tests

These tests focus on the main backend behavior that users interact with.

Examples:

- authentication and session handling
- onboarding pool creation
- round start, refresh, and pick submission
- game summaries and insights
- recommendation service behavior
- ML configuration loading and updates

Why this matters:

- These tests confirm that the game flow works as designed
- They help us catch logic bugs before users encounter them
- They make sure important edge cases are handled cleanly

Representative files:

- [test_auth_service.py](../backend/tests/services/test_auth_service.py)
- [test_game_play.py](../backend/tests/services/test_game_play.py)
- [test_game_service.py](../backend/tests/services/test_game_service.py)
- [test_game_insights.py](../backend/tests/services/test_game_insights.py)
- [test_recommender.py](../backend/tests/services/test_recommender.py)
- [test_ml_config.py](../backend/tests/services/test_ml_config.py)

## Model Testing Overview

The model tests are the most important part of our AI quality checks.

They are designed to answer four broad questions:

1. Is the model working?
2. Is the model learning from user choices?
3. Is the model stable over time?
4. Is the model robust when data is incomplete or unusual?

### What "working" means

For us, a working model means:

- product information can be converted into machine-readable features
- the internal user preference state updates when a player makes selections
- the scoring system can rank candidate products
- the recommendation engine returns valid outputs without crashing

### What "learning" means

The game is built around the idea that the AI should adapt to what the player chooses.

So we test whether:

- the user preference vector changes after picks
- recommendations respond to onboarding selections
- repeated rounds do not simply repeat the same stale outputs
- hidden preferences can be discovered from selection patterns

### What "stable" means

A model can still "run" even if it has quietly gotten worse.

To protect against that, we added baseline regression testing. This means:

- we run the model on a known validation dataset
- we save the expected quality scores from a known-good version
- future runs are compared against that baseline
- the tests fail if performance drops beyond an allowed tolerance

This helps us catch subtle degradation, not just complete breakage.

Files used for this:

- [movie_validation_fixture.json](../backend/tests/ml/fixtures/movie_validation_fixture.json)
- [movie_validation_baseline.json](../backend/tests/ml/fixtures/movie_validation_baseline.json)
- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)

### What "robust" means

Real-world data is not always clean.

Some products may have:

- missing metadata
- empty tags
- incomplete category details
- malformed numeric values
- very small candidate pools

We added robustness tests to make sure the model still behaves safely in these situations.

This does not mean the model will perform equally well on poor-quality data, but it should still remain stable and usable.

## Types of Model Tests We Added

### 1. Feature Extraction Tests

These tests check whether movie records are being turned into useful machine-readable signals.

In plain language, they confirm that:

- the model can "read" the data
- the feature matrix is populated
- known metadata such as genres is recognized properly
- the data produces meaningful vectors instead of empty ones

Why this matters:

- If feature extraction is broken, the rest of the model has very little to work with

Representative files:

- [test_feature_space.py](../backend/tests/ml/test_feature_space.py)
- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)

### 2. Model Quality Tests

These tests run the recommendation model against a movie validation dataset and measure whether the model surfaces relevant items.

We use standard recommendation quality signals such as:

- precision
  - how often the recommended items are actually relevant
- NDCG
  - whether better matches are ranked nearer the top
- hit rate
  - whether at least one relevant result appears in the recommendations

Why this matters:

- It tells us whether the model is producing recommendations that are at least directionally useful
- It gives us a repeatable quality bar for future changes

Representative files:

- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)

### 3. End-to-End Model Flow Tests

These tests simulate a simple multi-round journey:

- the user starts with onboarding picks
- the model builds an internal preference state
- the model recommends candidates in later rounds
- the user state continues to update

Why this matters:

- It checks the model as part of the actual game loop, not just in isolation

Representative files:

- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)

### 4. Regression Baseline Tests

These tests compare the current model’s results to a saved baseline.

We currently track things like:

- recommendation quality scores
- feature coverage
- diversity of candidates

Why this matters:

- A code change may not break the model completely, but it can still make it worse
- Regression tests are our early warning system for that kind of decline

Representative files:

- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)
- [movie_validation_fixture.json](../backend/tests/ml/fixtures/movie_validation_fixture.json)
- [movie_validation_baseline.json](../backend/tests/ml/fixtures/movie_validation_baseline.json)

### 5. Slice-Based Validation

For movies, we also look at quality across different slices of the dataset such as:

- language
- decade
- certification
- country

Why this matters:

- It helps us check whether the model is only working well for one narrow type of content
- It gives a first layer of bias and coverage monitoring

This is not a full fairness audit, but it is a meaningful step toward more balanced validation.

Representative files:

- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)

### 6. Noisy-Data Robustness Tests

These tests intentionally use imperfect movie records with missing or inconsistent information.

Why this matters:

- It helps us verify that the model remains dependable even when data quality is uneven
- It prepares the system for future ingestion changes and incomplete upstream records

Representative files:

- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)

### 7. Optional Live Database Validation

We also created an optional test path that can run against a real Postgres database.

This checks whether:

- the recommender can refresh using live stored products
- recommendation calls still succeed on real database content
- collaborative filtering can train when completed game rounds exist
- sparse live rows can still be processed

Why this matters:

- Curated test data is useful, but real stored data gives us an additional reality check
- We keep these tests optional so they do not make normal test runs flaky

Representative files:

- [test_model_validation_db.py](../backend/tests/ml/test_model_validation_db.py)

## Why We Use A Small Curated Movie Fixture

Originally, some movie validation depended on a large ingest checkpoint file.

We improved that by adding a small committed movie fixture inside the repo.

This gives us a few advantages:

- tests can run even when the large ingest checkpoint is missing
- the validation dataset is stable and repeatable
- model regression checks can run in a lightweight way
- contributors do not need a fully populated movie database just to run the core validation suite

We still support larger validation sources when available, but the curated fixture gives us a reliable baseline.

Reference files:

- [movie_validation_fixture.json](../backend/tests/ml/fixtures/movie_validation_fixture.json)
- [movie_validation_baseline.json](../backend/tests/ml/fixtures/movie_validation_baseline.json)
- [test_model_validation.py](../backend/tests/ml/test_model_validation.py)

## What These Tests Provide Confidence In

The testing work provides confidence that:

- the game experience is functioning correctly
- the recommendation model is not just running, but adapting to choices
- the model can be checked for quality after changes
- the system is better protected against silent regressions
- the application is more resilient to imperfect data
- the AI behavior is being measured in a structured, repeatable way

## What These Tests Do Not Claim

It is also important to be clear about what testing does not automatically prove.

These tests do not guarantee:

- perfect recommendations for every user
- perfect fairness across every possible subgroup
- complete protection against every future data issue
- real user satisfaction on their own

Those concerns are broader and usually require a mix of:

- testing
- real usage data
- product feedback
- iterative tuning

## Current Scope

The most complete model validation work currently focuses on `movies`.

This includes:

- feature extraction validation
- quality thresholds
- baseline regression checks
- slice-based checks
- noisy-data robustness tests
- optional live database validation

The same general approach can later be extended to `fountain_pens` and `games`.

## Summary

The tests are designed to show that the system works correctly, that the recommendation model learns from player choices, and that model quality can be monitored for instability or degradation over time.
