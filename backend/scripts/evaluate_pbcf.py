"""
Evaluate game AI performance from Postgres game data.

Usage:
    cd backend
    python -m scripts.evaluate_pbcf
    python -m scripts.evaluate_pbcf --category movies
"""

from __future__ import annotations

import argparse
import asyncio
from statistics import mean

from sqlalchemy import and_, func, select


async def evaluate(category: str | None = None) -> None:
    """Compute and print aggregate AI/game evaluation metrics from DB data."""
    from app.db import GameRecord, GameRoundRecord, get_db, init_db

    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)

    game_stmt = select(GameRecord).where(GameRecord.status == "completed")
    if category:
        game_stmt = game_stmt.where(GameRecord.category == category)
    games = (await db.execute(game_stmt)).scalars().all()

    if not games:
        print("No completed games found.")
        await db_gen.aclose()
        return

    game_ids = [g.id for g in games]
    rounds = (
        (
            await db.execute(
                select(GameRoundRecord).where(
                    and_(GameRoundRecord.game_id.in_(game_ids), GameRoundRecord.completed.is_(True))
                )
            )
        )
        .scalars()
        .all()
    )

    total_rounds = len(rounds)
    ai_correct = sum(1 for r in rounds if r.ai_correct)
    ai_exact = sum(1 for r in rounds if r.ai_pick_id and r.human_pick_id and r.ai_pick_id == r.human_pick_id)
    mean_rank = mean([float(r.ai_rank_of_pick) for r in rounds if r.ai_rank_of_pick is not None]) if rounds else 0.0
    mean_conf = mean([float(r.ai_confidence) for r in rounds if r.ai_confidence is not None]) if rounds else 0.0

    score_deltas = [int(g.human_score) - int(g.ai_score) for g in games]
    avg_delta = mean(score_deltas) if score_deltas else 0.0
    ai_wins = sum(1 for d in score_deltas if d < 0)
    human_wins = sum(1 for d in score_deltas if d > 0)
    ties = sum(1 for d in score_deltas if d == 0)

    per_category = (
        await db.execute(
            select(GameRecord.category, func.count(GameRecord.id))
            .where(GameRecord.status == "completed")
            .group_by(GameRecord.category)
        )
    ).all()

    print("=== PBCF/Game Evaluation ===")
    print(f"Completed games: {len(games)}")
    print(f"Completed rounds: {total_rounds}")
    print(f"Top-3 accuracy: {(ai_correct / total_rounds * 100) if total_rounds else 0:.2f}%")
    print(f"Exact-match accuracy: {(ai_exact / total_rounds * 100) if total_rounds else 0:.2f}%")
    print(f"Average rank of human pick in AI list: {mean_rank:.2f}")
    print(f"Average AI confidence score: {mean_conf:.3f}")
    print(f"Average score delta (human-ai): {avg_delta:.2f}")
    print(f"Game outcomes -> human wins: {human_wins}, ai wins: {ai_wins}, ties: {ties}")
    print("Completed games by category:")
    for cat, count in per_category:
        print(f"  {cat}: {count}")

    await db_gen.aclose()


def parse_args() -> argparse.Namespace:
    """Parse CLI options for evaluation script."""
    parser = argparse.ArgumentParser(description="Evaluate AI performance from Postgres game data")
    parser.add_argument("--category", default=None, help="Optional category filter")
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for evaluation script."""
    args = parse_args()
    asyncio.run(evaluate(category=args.category))


if __name__ == "__main__":
    main()
