"""
Evaluate game AI performance using real completed game data from MongoDB.

Generates reports on:
  - Overall AI accuracy (win rate)
  - AI accuracy by round number (learning curve)
  - Score distributions (human vs AI)
  - AI rank analysis (when wrong, how close was the AI?)
  - Model learning metrics over rounds (coherence, predicted prefix rating)

Usage:
    cd backend
    python -m scripts.evaluate_pbcf
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from pymongo import MongoClient

REPORTS_DIR = ROOT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def get_sync_db():
    """Get a synchronous pymongo connection (simpler for a standalone script)."""
    from app.db import settings
    client = MongoClient(settings.mongodb_url)
    return client[settings.mongodb_db_name]


# ── Data loading ────────────────────────────────────────────────────────────

def load_completed_games(db) -> list[dict]:
    """Load all completed games."""
    return list(db.games.find({"status": "completed"}).sort("created_at", 1))


def load_rounds_for_game(db, game_id) -> list[dict]:
    """Load all completed rounds for a game, sorted by round number."""
    return list(
        db.game_rounds.find({"game_id": game_id, "completed": True})
        .sort("round_number", 1)
    )


# ── Analysis functions ──────────────────────────────────────────────────────

def analyze_ai_accuracy(games: list[dict], rounds_by_game: dict) -> dict:
    """Overall AI accuracy across all games and rounds."""
    total_rounds = 0
    ai_correct_total = 0

    for game in games:
        gid = game["_id"]
        for rnd in rounds_by_game.get(gid, []):
            total_rounds += 1
            if rnd.get("ai_correct"):
                ai_correct_total += 1

    return {
        "total_games": len(games),
        "total_rounds": total_rounds,
        "ai_correct": ai_correct_total,
        "ai_accuracy": ai_correct_total / total_rounds if total_rounds else 0.0,
        "human_win_rate": 1 - (ai_correct_total / total_rounds) if total_rounds else 0.0,
    }


def analyze_accuracy_by_round(games: list[dict], rounds_by_game: dict, total_rounds: int = 5) -> dict[int, dict]:
    """AI accuracy broken down by round number — the core learning curve."""
    by_round: dict[int, dict] = {}

    for rn in range(1, total_rounds + 1):
        correct = 0
        total = 0
        for game in games:
            gid = game["_id"]
            for rnd in rounds_by_game.get(gid, []):
                if rnd["round_number"] == rn:
                    total += 1
                    if rnd.get("ai_correct"):
                        correct += 1

        by_round[rn] = {
            "total": total,
            "correct": correct,
            "accuracy": correct / total if total else 0.0,
        }

    return by_round


def analyze_score_distribution(games: list[dict]) -> dict:
    """Distribution of final human and AI scores across games."""
    human_scores = [g.get("human_score", 0) for g in games]
    ai_scores = [g.get("ai_score", 0) for g in games]
    deltas = [h - a for h, a in zip(human_scores, ai_scores)]

    human_wins = sum(1 for d in deltas if d > 0)
    ai_wins = sum(1 for d in deltas if d < 0)
    ties = sum(1 for d in deltas if d == 0)

    return {
        "human_scores": human_scores,
        "ai_scores": ai_scores,
        "deltas": deltas,
        "human_wins": human_wins,
        "ai_wins": ai_wins,
        "ties": ties,
        "avg_human_score": float(np.mean(human_scores)) if human_scores else 0.0,
        "avg_ai_score": float(np.mean(ai_scores)) if ai_scores else 0.0,
        "avg_delta": float(np.mean(deltas)) if deltas else 0.0,
    }


def analyze_ai_rank_when_wrong(games: list[dict], rounds_by_game: dict) -> dict:
    """When the AI is wrong, where did the human's pick rank in the AI's top-k?"""
    ranks = []

    for game in games:
        gid = game["_id"]
        for rnd in rounds_by_game.get(gid, []):
            if rnd.get("ai_correct"):
                continue
            top_k = rnd.get("ai_top_k", [])
            human_pick = rnd.get("human_pick_id")
            if not top_k or not human_pick:
                continue
            found = False
            for rank, entry in enumerate(top_k, start=1):
                if entry.get("product_id") == human_pick:
                    ranks.append(rank)
                    found = True
                    break
            if not found:
                ranks.append(len(top_k) + 1)  # outside top-k

    rank_counts: dict[int, int] = defaultdict(int)
    for r in ranks:
        rank_counts[r] += 1

    return {
        "wrong_rounds": len(ranks),
        "avg_rank_of_human_pick": float(np.mean(ranks)) if ranks else 0.0,
        "median_rank": float(np.median(ranks)) if ranks else 0.0,
        "rank_distribution": dict(sorted(rank_counts.items())),
        "in_top_3": sum(1 for r in ranks if r <= 3),
        "in_top_5": sum(1 for r in ranks if r <= 5),
    }


def analyze_learning_metrics(games: list[dict], rounds_by_game: dict, total_rounds: int = 5) -> dict:
    """Track coherence and predicted prefix rating evolution across rounds."""
    coherence_by_round: dict[int, list[float]] = defaultdict(list)
    ppr_by_round: dict[int, list[float]] = defaultdict(list)

    for game in games:
        gid = game["_id"]
        for rnd in rounds_by_game.get(gid, []):
            rn = rnd["round_number"]
            post = rnd.get("post_metrics", {})
            if "coherence_score" in post:
                coherence_by_round[rn].append(post["coherence_score"])
            if "predicted_prefix_rating" in post:
                ppr_by_round[rn].append(post["predicted_prefix_rating"])

    result = {}
    for rn in range(1, total_rounds + 1):
        result[rn] = {
            "avg_coherence": float(np.mean(coherence_by_round[rn])) if coherence_by_round[rn] else None,
            "avg_predicted_prefix_rating": float(np.mean(ppr_by_round[rn])) if ppr_by_round[rn] else None,
        }

    return result


# ── Plotting ────────────────────────────────────────────────────────────────

def plot_accuracy_by_round(by_round: dict[int, dict], path: Path):
    rounds = sorted(by_round.keys())
    accuracies = [by_round[r]["accuracy"] for r in rounds]

    plt.figure(figsize=(8, 5))
    plt.bar(rounds, accuracies, color="#4a90d9", edgecolor="white", linewidth=0.5)
    plt.axhline(y=np.mean(accuracies), color="#e74c3c", linestyle="--", label=f"Mean: {np.mean(accuracies):.1%}")
    plt.xlabel("Round Number")
    plt.ylabel("AI Accuracy")
    plt.title("AI Prediction Accuracy by Round")
    plt.xticks(rounds)
    plt.ylim(0, 1.05)
    plt.legend()
    plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def plot_score_distribution(dist: dict, path: Path):
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # Score comparison
    games_range = range(1, len(dist["human_scores"]) + 1)
    axes[0].bar([x - 0.2 for x in games_range], dist["human_scores"], 0.4, label="Human", color="#2ecc71")
    axes[0].bar([x + 0.2 for x in games_range], dist["ai_scores"], 0.4, label="AI", color="#e74c3c")
    axes[0].set_xlabel("Game")
    axes[0].set_ylabel("Score")
    axes[0].set_title("Human vs AI Scores per Game")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.3)

    # Delta histogram
    axes[1].hist(dist["deltas"], bins=range(-100, 110, 10), color="#3498db", edgecolor="white")
    axes[1].axvline(x=0, color="#e74c3c", linestyle="--", linewidth=2)
    axes[1].set_xlabel("Score Delta (Human - AI)")
    axes[1].set_ylabel("Number of Games")
    axes[1].set_title("Score Delta Distribution")
    axes[1].grid(axis="y", alpha=0.3)

    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def plot_learning_metrics(metrics: dict, path: Path):
    rounds = sorted(metrics.keys())
    coherence = [metrics[r]["avg_coherence"] for r in rounds]
    ppr = [metrics[r]["avg_predicted_prefix_rating"] for r in rounds]

    # Filter out None values
    valid_coh = [(r, c) for r, c in zip(rounds, coherence) if c is not None]
    valid_ppr = [(r, p) for r, p in zip(rounds, ppr) if p is not None]

    if not valid_coh and not valid_ppr:
        return

    fig, ax1 = plt.subplots(figsize=(8, 5))

    if valid_coh:
        rs, cs = zip(*valid_coh)
        ax1.plot(rs, cs, "o-", color="#2ecc71", label="Coherence Score")
    ax1.set_xlabel("Round Number")
    ax1.set_ylabel("Coherence Score", color="#2ecc71")
    ax1.tick_params(axis="y", labelcolor="#2ecc71")
    ax1.set_ylim(0, 1.05)

    if valid_ppr:
        ax2 = ax1.twinx()
        rs, ps = zip(*valid_ppr)
        ax2.plot(rs, ps, "s--", color="#9b59b6", label="Predicted Prefix Rating")
        ax2.set_ylabel("Predicted Prefix Rating", color="#9b59b6")
        ax2.tick_params(axis="y", labelcolor="#9b59b6")
        ax2.set_ylim(1, 5.2)

    plt.title("Model Learning Metrics by Round")
    ax1.set_xticks(rounds)
    ax1.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


# ── Report generation ───────────────────────────────────────────────────────

def generate_summary(
    accuracy: dict,
    by_round: dict[int, dict],
    scores: dict,
    rank_analysis: dict,
    learning: dict,
) -> str:
    lines = [
        "=" * 60,
        "  RECOMMENDLE — AI PERFORMANCE EVALUATION",
        f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 60,
        "",
        "OVERVIEW",
        f"  Completed games analyzed: {accuracy['total_games']}",
        f"  Total rounds analyzed:    {accuracy['total_rounds']}",
        "",
        "AI ACCURACY",
        f"  Overall AI accuracy:   {accuracy['ai_accuracy']:.1%}  ({accuracy['ai_correct']}/{accuracy['total_rounds']} rounds)",
        f"  Human unpredictability: {accuracy['human_win_rate']:.1%}",
        "",
        "GAME OUTCOMES",
        f"  Human wins: {scores['human_wins']}  |  AI wins: {scores['ai_wins']}  |  Ties: {scores['ties']}",
        f"  Avg human score: {scores['avg_human_score']:.1f}  |  Avg AI score: {scores['avg_ai_score']:.1f}",
        f"  Avg score delta (human - AI): {scores['avg_delta']:+.1f}",
        "",
        "AI ACCURACY BY ROUND (Learning Curve)",
    ]

    for rn in sorted(by_round.keys()):
        data = by_round[rn]
        bar = "█" * int(data["accuracy"] * 20)
        lines.append(f"  Round {rn:2d}: {data['accuracy']:5.1%}  {bar}  ({data['correct']}/{data['total']})")

    lines.extend([
        "",
        "AI RANK ANALYSIS (When AI Was Wrong)",
        f"  Rounds where AI was wrong: {rank_analysis['wrong_rounds']}",
        f"  Avg rank of human's pick in AI's list: {rank_analysis['avg_rank_of_human_pick']:.1f}",
        f"  Median rank: {rank_analysis['median_rank']:.0f}",
        f"  Human's pick was in AI's top 3: {rank_analysis['in_top_3']}  ({rank_analysis['in_top_3']/max(rank_analysis['wrong_rounds'],1):.0%})",
        f"  Human's pick was in AI's top 5: {rank_analysis['in_top_5']}  ({rank_analysis['in_top_5']/max(rank_analysis['wrong_rounds'],1):.0%})",
    ])

    if rank_analysis["rank_distribution"]:
        lines.append("  Rank distribution:")
        for rank, count in sorted(rank_analysis["rank_distribution"].items()):
            label = f"#{rank}" if rank <= 10 else "Outside top-k"
            lines.append(f"    {label}: {count}")

    lines.extend([
        "",
        "MODEL LEARNING METRICS (Avg across games)",
    ])
    for rn in sorted(learning.keys()):
        data = learning[rn]
        coh = f"{data['avg_coherence']:.3f}" if data["avg_coherence"] is not None else "N/A"
        ppr = f"{data['avg_predicted_prefix_rating']:.2f}" if data["avg_predicted_prefix_rating"] is not None else "N/A"
        lines.append(f"  Round {rn:2d}: coherence={coh}  predicted_rating={ppr}")

    lines.append("")
    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to MongoDB...")
    db = get_sync_db()

    games = load_completed_games(db)
    if not games:
        print("\n⚠  No completed games found in the database.")
        print("   Play at least one full game at http://localhost:5173 then run this again.")
        return

    print(f"Found {len(games)} completed game(s). Analyzing...\n")

    # Load all rounds
    rounds_by_game: dict = {}
    for game in games:
        rounds_by_game[game["_id"]] = load_rounds_for_game(db, game["_id"])

    # Run analyses
    accuracy = analyze_ai_accuracy(games, rounds_by_game)
    by_round = analyze_accuracy_by_round(games, rounds_by_game)
    scores = analyze_score_distribution(games)
    rank_analysis = analyze_ai_rank_when_wrong(games, rounds_by_game)
    learning = analyze_learning_metrics(games, rounds_by_game)

    # Generate summary
    summary = generate_summary(accuracy, by_round, scores, rank_analysis, learning)
    print(summary)

    summary_path = REPORTS_DIR / "evaluation_summary.txt"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"Summary saved to {summary_path}")

    # Generate plots
    plot_accuracy_by_round(by_round, REPORTS_DIR / "ai_accuracy_by_round.png")
    plot_score_distribution(scores, REPORTS_DIR / "score_distribution.png")
    plot_learning_metrics(learning, REPORTS_DIR / "learning_metrics.png")
    print(f"Plots saved to {REPORTS_DIR}/")

    # Also save raw data as JSON for programmatic use
    raw = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "accuracy": accuracy,
        "accuracy_by_round": {str(k): v for k, v in by_round.items()},
        "score_distribution": {
            k: v for k, v in scores.items()
            if k not in ("human_scores", "ai_scores", "deltas")
        },
        "rank_analysis": {
            k: v for k, v in rank_analysis.items()
            if k != "rank_distribution"
        },
    }
    json_path = REPORTS_DIR / "evaluation_data.json"
    json_path.write_text(json.dumps(raw, indent=2, default=str), encoding="utf-8")
    print(f"Raw data saved to {json_path}")


if __name__ == "__main__":
    main()
