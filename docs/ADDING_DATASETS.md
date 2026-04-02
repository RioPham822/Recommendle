# Adding New Datasets

This project supports multiple categories through category profiles plus category-specific product payloads stored in Postgres.

Current built-in categories:
- `fountain_pens`
- `movies`
- `games`

## How Categories Work

Product storage:
- table: `products`
- category id: `ProductRecord.category`
- category payload: `ProductRecord.data`

Core extension points:
- `backend/app/category_profiles.py`
- `backend/app/services/game_service.py`
- `backend/app/ml/prefix_cf.py`
- ingestion scripts under `backend/scripts/`

The important design choice is that most category behavior comes from normalized payload keys and the category profile, not from custom database columns.

## Step-By-Step

### 1. Pick a category id

Example:
- `chairs`

### 2. Normalize your dataset fields

Reuse shared keys whenever possible:
- `title`
- `vendor`
- `tags`
- `images`
- `description`
- `url`
- `price_min`
- `price_max`

Add category-specific fields only when needed:
- `material`
- `color`
- `seat_height_cm`

### 3. Add a `CategoryProfile`

Add a new entry to `_CATEGORY_PROFILES` in `backend/app/category_profiles.py`.

Define:
- labels and copy text
- `categorical_fields`
- `multi_fields`
- `numeric_fields`
- card/detail display fields

### 4. Ingest the dataset

Each stored product should look like:
- `category = "<your_category>"`
- `data = { ... normalized payload ... }`

Follow the existing patterns in:
- `backend/scripts/load_db.py`
- `backend/scripts/ingest_movies_tmdb.py`
- `backend/scripts/ingest_games_igdb.py`

### 5. Verify category availability

Run:

```bash
curl http://localhost:8015/api/game/categories
```

The new category should appear with a count.

### 6. Make sure the category is actually playable

Verify:
- onboarding can be generated
- round candidates can be generated
- final summary completes
- cards display meaningful fields

Notes:
- the current frontend expects at least 100 visible items before it treats a category as ready
- movie-like visibility filters may affect the visible count if you add custom filtering logic

## Modeling Guidance

Use one normalized key per concept:
- prefer `color` over `colour`, `ColorName`, and other variants

Reuse shared semantics across categories:
- if two domains both have a notion of brand/studio/vendor, normalize to `vendor`

Keep payloads practical for UI display:
- include image URLs when possible
- include enough text fields for detail views and explanations

## Where Category-Specific Logic Still Exists

Most of the system is profile-driven, but some presentation logic still lives in service code.

Current examples:
- `_product_card()` in `backend/app/services/game_service.py`
- category-specific display labels in `backend/app/category_profiles.py`

If you want fully config-only category onboarding and display behavior, the next step would be moving more card subtitle and badge logic into the profile layer.
