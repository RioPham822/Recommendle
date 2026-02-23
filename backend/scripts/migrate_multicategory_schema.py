"""
Legacy schema migration script placeholder.

The backend now uses a Postgres-backed document store.
"""

from __future__ import annotations


def main() -> None:
    """Print no-op notice for deprecated legacy migration path."""
    print("No action required: category compatibility checks now run at API startup " "against the Postgres-backed store.")


if __name__ == "__main__":
    main()
