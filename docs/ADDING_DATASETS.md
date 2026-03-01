# Adding New Datasets

This project supports multiple categories (for example `fountain_pens`, `movies`) through category profiles and product JSON payloads.

## Current State
- Product data is stored in Postgres in `products` with:
  - `category` (string)
  - `data` (JSONB payload)
- Product API responses are category-agnostic:
  - `/api/products*` returns `ProductOut` with core fields plus `data`
  - Game cards expose common card fields plus `attributes` for category-specific values
- Feature extraction is driven by `backend/app/category_profiles.py`.
- Gameplay/recommendation code reads fields through normalized payload keys.
- Game services now derive feature/card field projections from category profiles in `game_service.py` via:
  - `_feature_projection(category)`
  - `_card_projection(category)`

This means you can add new datasets without adding DB columns, but you still need to define category semantics.

## Add A New Category (Step-by-Step)
1. Pick a category id.
- Example: `chairs`

2. Define normalized keys in your dataset.
- Reuse shared keys where possible:
  - `title`, `vendor`, `tags`, `price_min`, `price_max`, `images`
- Add category-specific keys when needed:
  - Example for chairs: `material`, `color`, `seat_height_cm`

3. Add a category profile in `backend/app/category_profiles.py`.
- Add entry in `_CATEGORY_PROFILES` with:
  - display labels
  - `categorical_fields`
  - `multi_fields`
  - `numeric_fields`

4. Ingest data into `products`.
- Store each item as:
  - `category = "<your_category>"`
  - `data = { ... normalized payload ... }`
- Follow patterns from `backend/scripts/load_db.py` and `backend/scripts/ingest_movies_tmdb.py`.

5. Verify category appears.
- Run API and call:
  - `GET /api/game/categories`

6. Play-test flow.
- Start game for new category:
  - `POST /api/game/start` with `"category": "<your_category>"`
- Confirm onboarding, round generation, and summary work.

## Important Modeling Guidance
- Use shared semantic keys for shared concepts across datasets.
  - Example: both chairs and tables can use `color`.
- Keep category-specific keys only when truly unique.
- Avoid exploding key variants for same meaning (`colour`, `ColorName`, etc.); normalize to one key.

## Long-Term Scalability Recommendation
The biggest remaining category-specific logic is presentation behavior (for example subtitle/badges in `_product_card`).
If you want fully config-only category onboarding, move display mapping into a category UI schema (or extend `CategoryProfile`) so no service code changes are needed for new categories.
