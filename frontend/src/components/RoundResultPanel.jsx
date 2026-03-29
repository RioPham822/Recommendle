import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import CancelRoundedIcon from '@mui/icons-material/CancelRounded';

function ResultFocusCard({ title, product, accent }) {
  return (
    <article className={`result-focus-card ${accent}`}>
      <span className="result-focus-card__label">{title}</span>
      <div className="result-focus-card__media">
        {product.image_url ? (
          <img src={product.image_url} alt={product.title} loading="lazy" />
        ) : (
          <div className="result-focus-card__fallback">No image</div>
        )}
      </div>
      <strong>{product.title}</strong>
      <p>{product.subtitle || product.vendor || 'Unknown'}</p>
    </article>
  );
}

export default function RoundResultPanel({ result, categoryCopy = {}, onNext, loadingNext }) {
  if (!result) return null;

  const isMatch = result.preference_match;
  const singular = categoryCopy.item_singular || 'item';
  const outcomeTitle = isMatch ? 'Preference Match!' : 'Not a match yet';
  const outcomeCopy = isMatch
    ? `The AI included your ${singular} in its top 5 picks, so your streak grew.`
    : `Your ${singular} was outside the AI's top 5, so the streak resets and the model has to learn again.`;

  return (
    <section className="screen shell result-screen">
      <div className={`panel result-banner ${isMatch ? 'success' : 'miss'}`}>
        <div className="result-banner__icon">
          {isMatch ? <CheckCircleRoundedIcon fontSize="large" /> : <CancelRoundedIcon fontSize="large" />}
        </div>
        <div>
          <p className="eyebrow">Round {result.round_number} outcome</p>
          <h2>{outcomeTitle}</h2>
          <p>{outcomeCopy}</p>
        </div>
        <div className="result-banner__streak">
          <span>Current streak</span>
          <strong>{result.current_match_streak} / {result.match_streak_target}</strong>
        </div>
      </div>

      <div className="result-focus-grid">
        <ResultFocusCard title={`Your ${singular}`} product={result.human_pick} accent="human" />
        <ResultFocusCard title={`AI's top pick`} product={result.ai_pick} accent="ai" />
      </div>

      <div className="panel">
        <div className="result-panel__header">
          <div>
            <p className="eyebrow">AI's top 5 picks</p>
            <h3>What the model thought you would choose</h3>
          </div>
          <span>{Math.round((result.rounds_played / Math.max(result.match_streak_target, 1)) * 100)}% into this run</span>
        </div>
        <p className="result-panel__copy">{result.ai_explanation.reason}</p>

        {result.ai_explanation.current_match_features?.length > 0 && (
          <div className="result-pill-group">
            {result.ai_explanation.current_match_features.map((feature) => (
              <span key={feature} className="feature-tag positive">{feature}</span>
            ))}
          </div>
        )}

        <ul className="result-top-list">
          {result.ai_explanation.top_candidates.map((candidate, index) => {
            const matched = candidate.id === result.human_pick.id;
            return (
              <li key={candidate.id} className={`result-top-list__item ${matched ? 'matched' : ''}`}>
                <div className="result-top-list__rank">#{index + 1}</div>
                <div className="result-top-list__media">
                  {candidate.image_url ? (
                    <img src={candidate.image_url} alt={candidate.title} loading="lazy" />
                  ) : (
                    <div className="result-top-list__fallback">No image</div>
                  )}
                </div>
                <div className="result-top-list__body">
                  <strong>{candidate.title}</strong>
                  <span>{candidate.subtitle || candidate.vendor || 'Unknown'}</span>
                  <div className="tag-list">
                    {(candidate.predicted_match_features || []).slice(0, 5).map((feature) => (
                      <span key={feature}>{feature}</span>
                    ))}
                  </div>
                </div>
                <div className="result-top-list__meta">
                  <span>{candidate.score.toFixed(2)}</span>
                  {matched && <CheckCircleRoundedIcon fontSize="small" />}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {(result.ai_explanation.learned_preferences?.length > 0 || result.ai_explanation.learned_dislikes?.length > 0) && (
        <div className="result-details-grid">
          <div className="panel">
            <p className="eyebrow">What the AI thinks you like</p>
            <div className="result-pill-group">
              {result.ai_explanation.learned_preferences.slice(0, 6).map(([name]) => (
                <span key={name} className="feature-tag positive">{name}</span>
              ))}
            </div>
          </div>
          <div className="panel">
            <p className="eyebrow">What the AI is moving away from</p>
            <div className="result-pill-group">
              {result.ai_explanation.learned_dislikes.slice(0, 6).map(([name]) => (
                <span key={name} className="feature-tag negative">{name}</span>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="round-actions round-actions--end">
        <button type="button" onClick={onNext} disabled={loadingNext}>
          {loadingNext ? 'Loading...' : result.game_complete ? 'View final summary' : 'Next round'}
        </button>
      </div>
    </section>
  );
}
