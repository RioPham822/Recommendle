"""Category profile metadata and feature token/humanization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_CATEGORY = "fountain_pens"


@dataclass(frozen=True)
class CategoryProfile:
    """Describes per-category labels and model feature fields."""

    id: str
    display_name: str
    item_singular: str
    item_plural: str
    vendor_label: str
    mode_caption: str
    onboarding_action: str
    top_recommendations_label: str
    hidden_gems_label: str
    hidden_gems_subtitle: str
    round_mode: str
    redundant_tokens: tuple[str, ...]
    categorical_fields: tuple[str, ...]
    multi_fields: tuple[str, ...]
    numeric_fields: tuple[str, ...]
    card_display_fields: tuple[str, ...]
    detail_display_fields: tuple[str, ...]
    hidden_tag_tokens: tuple[str, ...]


_CATEGORY_PROFILES: dict[str, CategoryProfile] = {
    "fountain_pens": CategoryProfile(
        id="fountain_pens",
        display_name="Fountain Pens",
        item_singular="pen",
        item_plural="pens",
        vendor_label="Brand",
        mode_caption="Visual mode prioritizes product imagery. Feature mode emphasizes vendor, price, and tag signals.",
        onboarding_action="Choose 10 pens from a pool of 50 to build your taste profile.",
        top_recommendations_label="AI's Top 5 Picks for You",
        hidden_gems_label="Hidden Gems - Patterns You Might Not Have Noticed",
        hidden_gems_subtitle="Pens You Didn't Know You'd Love",
        round_mode="classic",
        redundant_tokens=(
            "fountain pens",
            "fountain pen",
            "pens",
            "pen",
            "ink",
            "inks",
            "writing",
            "stationery",
            "hideoos",
            "bis-hidden",
            "products",
        ),
        categorical_fields=("vendor", "product_type"),
        multi_fields=("tags", "options"),
        numeric_fields=("price_min", "price_max"),
        card_display_fields=("vendor", "price", "nib_size", "tags"),
        detail_display_fields=("description", "nib_sizes", "tags", "url"),
        hidden_tag_tokens=(
            "products",
            "pens",
            "hideoos",
            "bis-hidden",
            "gpc-oversize",
            "yafa-pen",
            "pens-lifetime",
        ),
    ),
    "movies": CategoryProfile(
        id="movies",
        display_name="Movies",
        item_singular="movie",
        item_plural="movies",
        vendor_label="Studio",
        mode_caption="Visual mode prioritizes posters. Feature mode emphasizes genre, studio, runtime, and rating signals.",
        onboarding_action="Choose 10 movies from a pool of 50 to build your taste profile.",
        top_recommendations_label="AI's Top 5 Movies for You",
        hidden_gems_label="Hidden Gems - Patterns You Might Not Have Noticed",
        hidden_gems_subtitle="Movies You Didn't Know You'd Love",
        round_mode="duel",
        redundant_tokens=("movie", "movies", "film", "films"),
        categorical_fields=(
            "vendor",
            "primary_country",
            "original_language",
            "certification",
            "decade_bucket",
            "runtime_bucket",
        ),
        multi_fields=("genres", "keywords", "production_companies", "directors"),
        numeric_fields=("release_year", "runtime_minutes", "vote_average", "popularity"),
        card_display_fields=("release_year", "genres", "runtime_minutes", "vote_average"),
        detail_display_fields=(
            "description",
            "directors",
            "certification",
            "original_language",
            "primary_country",
            "production_companies",
            "keywords",
            "url",
        ),
        hidden_tag_tokens=("movie", "movies", "film", "films"),
    ),
}


def supported_categories() -> list[str]:
    """Return all configured category identifiers."""
    return list(_CATEGORY_PROFILES.keys())


def normalize_category(value: str | None) -> str:
    """Normalize and validate a category input value."""
    if value is None:
        return DEFAULT_CATEGORY
    normalized = value.strip().lower()
    if normalized in _CATEGORY_PROFILES:
        return normalized
    raise ValueError(f"Unsupported category '{value}'")


def get_category_profile(category: str | None) -> CategoryProfile:
    """Return profile metadata for a normalized category."""
    return _CATEGORY_PROFILES[normalize_category(category)]


def category_copy(category: str | None) -> dict[str, str]:
    """Return frontend-friendly copy text for a category."""
    profile = get_category_profile(category)
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "item_singular": profile.item_singular,
        "item_plural": profile.item_plural,
        "vendor_label": profile.vendor_label,
        "mode_caption": profile.mode_caption,
        "onboarding_action": profile.onboarding_action,
        "top_recommendations_label": profile.top_recommendations_label,
        "hidden_gems_label": profile.hidden_gems_label,
        "hidden_gems_subtitle": profile.hidden_gems_subtitle,
        "round_mode": profile.round_mode,
    }


def category_display_schema(category: str | None) -> dict[str, Any]:
    """Return per-category field schema used by frontend cards and detail popovers."""
    profile = get_category_profile(category)
    return {
        "card_fields": [
            {
                "key": field,
                "label": profile.vendor_label if field == "vendor" else _display_field_label(field),
                "type": _display_field_type(field),
            }
            for field in profile.card_display_fields
        ],
        "detail_fields": [
            {
                "key": field,
                "label": profile.vendor_label if field == "vendor" else _display_field_label(field),
                "type": _display_field_type(field),
            }
            for field in profile.detail_display_fields
        ],
        "tag_limit_card": 3,
        "tag_limit_detail": 8,
    }


def _value_for_field(product: Any, field: str) -> Any:
    """Read a field from dict/object product payloads safely."""
    if isinstance(product, dict):
        return product.get(field)
    direct = getattr(product, field, None)
    if direct is not None:
        return direct
    payload = getattr(product, "data", None)
    if isinstance(payload, dict):
        return payload.get(field)
    return None


def _to_slug(value: Any) -> str:
    """Normalize free text into a stable lowercase token fragment."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("/", " ")
    text = text.replace("&", " and ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text


def extract_feature_tokens(product: Any, category: str | None) -> tuple[list[str], dict[str, float]]:
    """Extract categorical tokens and numeric feature values for a product."""
    profile = get_category_profile(category)
    tokens: list[str] = []
    numeric_values: dict[str, float] = {}

    for field in profile.categorical_fields:
        value = _value_for_field(product, field)
        slug = _to_slug(value)
        if slug:
            tokens.append(f"cat::{profile.id}::cat::{field}::{slug}")

    for field in profile.multi_fields:
        value = _value_for_field(product, field)
        if field == "options" and isinstance(value, dict):
            for opt_name, opt_values in value.items():
                opt_slug = _to_slug(opt_name)
                if not opt_slug:
                    continue
                if not isinstance(opt_values, list):
                    continue
                for opt_value in opt_values:
                    value_slug = _to_slug(opt_value)
                    if value_slug:
                        tokens.append(f"cat::{profile.id}::multi::option::{opt_slug}|{value_slug}")
            continue

        if isinstance(value, list):
            for item in value:
                slug = _to_slug(item)
                if slug:
                    tokens.append(f"cat::{profile.id}::multi::{field}::{slug}")

    for field in profile.numeric_fields:
        value = _value_for_field(product, field)
        if value is None:
            continue
        try:
            numeric_values[f"cat::{profile.id}::num::{field}_z"] = float(value)
        except (TypeError, ValueError):
            continue

    return tokens, numeric_values


def is_numeric_feature_key(raw: str) -> bool:
    """Return True when a token encodes numeric feature dimension."""
    return "::num::" in raw


def _field_label(field: str) -> str:
    """Map raw field names to short display labels."""
    mapping = {
        "product_type": "Type",
        "primary_country": "Country",
        "original_language": "Language",
        "certification": "Rating",
        "decade_bucket": "Decade",
        "runtime_bucket": "Runtime",
        "genres": "Genre",
        "keywords": "Keyword",
        "production_companies": "Studio",
        "directors": "Director",
    }
    return mapping.get(field, field.replace("_", " ").title())


def _display_field_label(field: str) -> str:
    """Return UX labels for card/detail rendering fields."""
    mapping = {
        "price": "Price",
        "nib_size": "Nib Size",
        "nib_sizes": "Nib Sizes",
        "release_year": "Year",
        "runtime_minutes": "Runtime",
        "vote_average": "Rating",
        "genres": "Genres",
        "description": "Description",
        "url": "Source",
    }
    return mapping.get(field, _field_label(field))


def _display_field_type(field: str) -> str:
    """Return frontend display type for one configured field."""
    if field in {"price"}:
        return "price"
    if field in {"release_year", "runtime_minutes", "vote_average"}:
        return "number"
    if field in {"genres", "tags", "keywords", "directors", "production_companies", "nib_sizes"}:
        return "list"
    if field in {"description"}:
        return "long_text"
    if field in {"url"}:
        return "link"
    return "text"


def clean_display_tags(category: str | None, tags: list[str] | None, limit: int = 8) -> list[str]:
    """Filter noisy/system tags and return a short user-facing list."""
    if not tags:
        return []
    profile = get_category_profile(category)
    hidden = {token.lower() for token in profile.hidden_tag_tokens}
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        tag = (raw or "").strip()
        if not tag:
            continue
        slug = tag.lower()
        if slug in hidden:
            continue
        if slug in seen:
            continue
        seen.add(slug)
        cleaned.append(tag)
        if len(cleaned) >= limit:
            break
    return cleaned


def humanize_feature(raw: str) -> str | None:
    """Convert raw feature token into user-facing text, skipping noisy labels."""
    parts = raw.split("::")
    if len(parts) < 5 or parts[0] != "cat":
        return raw.title()

    category = parts[1]
    profile = get_category_profile(category)
    kind = parts[2]
    field = parts[3]
    value = "::".join(parts[4:])

    value_text = value.replace("|", " ").replace("_", " ").strip().title()
    if value_text.lower() in {t.lower() for t in profile.redundant_tokens}:
        return None

    if kind == "cat":
        if field == "vendor":
            return value_text
        if field == "product_type" and value_text.lower() in {t.lower() for t in profile.redundant_tokens}:
            return None
        label = _field_label(field)
        return value_text if label in {"Type"} else f"{value_text} {label}"

    if kind == "multi":
        if field == "option":
            if "|" in value:
                opt_name, opt_value = value.split("|", 1)
                return f"{opt_value.replace('_', ' ').title()} {opt_name.replace('_', ' ').title()}"
            return value_text
        return value_text

    if kind == "num":
        return None

    return value_text


def humanize_feature_list(raw_list: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Humanize and deduplicate feature labels while preserving order."""
    seen: set[str] = set()
    results: list[tuple[str, float]] = []
    for raw, weight in raw_list:
        label = humanize_feature(raw)
        if not label:
            continue
        key = label.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        results.append((label, weight))
    return results


def numeric_preference_label(raw: str, weight: float) -> str:
    """Return semantic label for numeric-feature preference direction."""
    parts = raw.split("::")
    if len(parts) < 4:
        return "Numeric Preference"
    field = parts[3].replace("_z", "")
    positive = weight >= 0

    if field.startswith("price_"):
        return "Higher Price Range" if positive else "Lower Price Range"
    if field == "runtime_minutes":
        return "Longer Runtime" if positive else "Shorter Runtime"
    if field == "release_year":
        return "Newer Releases" if positive else "Older Releases"
    if field == "vote_average":
        return "Higher Rated Titles" if positive else "Lower Rated Titles"
    if field == "popularity":
        return "Popular Titles" if positive else "Niche Titles"
    return f"{field.replace('_', ' ').title()} Preference"
