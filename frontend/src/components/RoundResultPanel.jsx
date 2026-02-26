import { formatPrice } from '../lib/api';

function ResultCard({ label, product, variant, showScore = false }) {
  const isMovie = product.category === 'movies';
  const priceText = formatPrice(product.price_min, product.price_max);
  const metaText = product.meta_badges?.length > 0 ? product.meta_badges.join(' · ') : '';
  const secondary = product.subtitle || product.vendor || 'Unknown';

  return (
    <div className={`result-card ${variant}`}>
      <h4>{label}</h4>
      <p className="result-title">{product.title}</p>
      <p className="muted">
        {secondary}{isMovie && metaText ? ` · ${metaText}` : (!isMovie ? ` · ${priceText}` : '')}
      </p>
      {showScore && product.score != null && (
        <p className="score-pill">AI Score {product.score.toFixed(2)}</p>
      )}
    </div>
  );
}

function FeatureTag({ name }) {
  return <span className="feature-tag">{name}</span>;
}

export default function RoundResultPanel({ result, categoryCopy = {}, onNext, loadingNext }) {
  if (!result) return null;

  const { ai_correct, ai_exact, ai_rank_of_pick, ai_explanation, post_round_metrics } = result;
  const singular = categoryCopy.item_singular || 'item';
  const isDuel = result.round_mode === 'duel';

  const outcomeClass = ai_correct ? 'outcome-ai' : 'outcome-human';
  const outcomeText = isDuel
    ? (ai_correct ? 'AI Won This Duel' : 'You Won This Duel')
    : (
      ai_correct
        ? (ai_exact ? 'AI Exact Match!' : `AI Top-3 Hit (Rank #${ai_rank_of_pick})`)
        : `AI Missed - Your pick was #${ai_rank_of_pick}`
    );

  return (
    <section className="screen shell">
      <div className={`outcome-banner ${outcomeClass}`}>
        <span className="outcome-label">{outcomeText}</span>
        <div className="scoreline">
          <span>You +{result.human_points}</span>
          <span>AI +{result.ai_points}</span>
        </div>
      </div>

      <header className="section-header">
        <div>
          <p className="eyebrow">Round {result.round_number} Results</p>
          <h2>Score: You {result.total_human_score} - AI {result.total_ai_score}</h2>
        </div>
      </header>

      <div className="result-grid">
        <ResultCard label={`Your ${singular}`} product={result.human_pick} variant="human-pick" />
        <ResultCard label={`AI's #1 ${singular}`} product={result.ai_pick} variant="ai-pick" showScore />
      </div>

      <div className="panel result-details">
        <h3>AI Reasoning</h3>
        <p>{ai_explanation.reason}</p>

        <h4 style={{ marginTop: '1rem', fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)' }}>
          {isDuel ? 'Duel Candidate Scores' : "AI's Top 5 Candidates"}
        </h4>
        <ul>
          {ai_explanation.top_candidates.map((c, i) => (
            <li key={c.id} className={`candidate-item ${result.human_pick.id === c.id ? 'matched' : ''}`}>
              <span>
                <strong style={{ marginRight: '0.4rem', color: 'var(--ink-faint)' }}>#{i + 1}</strong>
                {c.title}
              </span>
              <strong>{c.score.toFixed(2)}</strong>
              <div className="candidate-preview">
                <div className="candidate-preview-media">
                  {c.image_url ? (
                    <img src={c.image_url} alt={c.title} loading="lazy" />
                  ) : (
                    <div className="candidate-preview-noimg">No image</div>
                  )}
                </div>
                <div className="candidate-preview-body">
                  <p className="candidate-preview-title">{c.title}</p>
                  <p className="candidate-preview-subtitle">{c.subtitle || c.vendor || 'Unknown'}</p>
                  {Object.entries(c.attributes || {}).slice(0, 4).map(([key, value]) => (
                    <p key={key} className="candidate-preview-attr">
                      <strong>{key.replace(/_/g, ' ')}</strong>: {Array.isArray(value) ? value.slice(0, 2).join(', ') : String(value)}
                    </p>
                  ))}
                  <div className="tag-list">
                    {[...(c.meta_badges || []), ...((c.tags || []).slice(0, 3))].map((token) => (
                      <span key={token}>{token}</span>
                    ))}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>

        {ai_explanation.shared_features?.length > 0 && (
          <div style={{ marginTop: '0.75rem' }}>
            <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
              Shared Features (Your Pick ∩ AI Pick)
            </h4>
            <div className="tag-list">
              {ai_explanation.shared_features.map((f) => (
                <FeatureTag key={f} name={f} />
              ))}
            </div>
          </div>
        )}

        {ai_explanation.learned_preferences?.length > 0 && (
          <div style={{ marginTop: '0.75rem' }}>
            <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
              What the AI Thinks You Like
            </h4>
            <div className="tag-list">
              {ai_explanation.learned_preferences.slice(0, 6).map(([name]) => (
                <span key={name} className="feature-tag positive">
                  {name}
                </span>
              ))}
            </div>
          </div>
        )}

        {result.round_number >= 4 && ai_explanation.hidden_preferences?.length > 0 && (() => {
          const learnedNames = new Set(
            (ai_explanation.learned_preferences || []).slice(0, 6).map(([n]) => n.toLowerCase()),
          );
          const uniqueHidden = ai_explanation.hidden_preferences.filter(
            ([n]) => !learnedNames.has(n.toLowerCase()),
          );
          if (uniqueHidden.length === 0) return null;
          return (
            <div style={{ marginTop: '0.75rem' }} className="hidden-patterns-hint">
              <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--accent-hidden)', marginBottom: '0.4rem' }}>
                Hidden Patterns Emerging
              </h4>
              <div className="tag-list">
                {uniqueHidden.map(([name]) => (
                  <span key={name} className="feature-tag hidden">{name}</span>
                ))}
              </div>
              {ai_explanation.hidden_preference_hints?.map((hint, i) => (
                <p key={i} className="hint-text">{hint}</p>
              ))}
            </div>
          );
        })()}
      </div>

      <div className="metric-strip" style={{ justifyContent: 'center' }}>
        <span>Coherence {post_round_metrics.coherence_score.toFixed(2)}</span>
        <span>Predicted Rating {post_round_metrics.predicted_prefix_rating.toFixed(2)}</span>
      </div>

      <div className="round-actions">
        <button type="button" onClick={onNext} disabled={loadingNext}>
          {loadingNext ? 'Loading...' : result.game_complete ? 'View Final Summary' : 'Next Round ->'}
        </button>
      </div>
    </section>
  );
}
