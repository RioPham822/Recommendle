import React from 'react';
import ProductCard from './ProductCard';

export default function RoundArena({
  round,
  totalRounds,
  humanScore,
  aiScore,
  mode,
  categoryCopy = {},
  selectedPick,
  onSelectPick,
  onSubmitPick,
  submitting,
}) {
  if (!round) {
    return null;
  }

  const singular = categoryCopy.item_singular || 'item';

  return (
    <section className="screen shell">
      <header className="section-header">
        <div>
          <p className="eyebrow">Gameplay</p>
          <h2>Round {round.round_number} of {totalRounds}</h2>
        </div>
        <div className="scoreline">
          <span>You: {humanScore}</span>
          <span>AI: {aiScore}</span>
        </div>
      </header>

      <div className="metric-strip">
        <span>Coherence {round.pre_round_metrics.coherence_score.toFixed(2)}</span>
        <span>Predicted Set Rating {round.pre_round_metrics.predicted_prefix_rating.toFixed(2)}</span>
      </div>

      <div className="pool-grid candidates">
        {round.candidates.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            mode={mode}
            selected={selectedPick === product.id}
            onClick={() => onSelectPick(product.id)}
            compact
          />
        ))}
      </div>

      <div className="round-actions">
        <button
          type="button"
          onClick={onSubmitPick}
          disabled={submitting || !selectedPick}
        >
          {submitting ? 'Submitting pick...' : `Lock In ${singular}`}
        </button>
      </div>
    </section>
  );
}
