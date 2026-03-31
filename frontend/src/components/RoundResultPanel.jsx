import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import CancelRoundedIcon from '@mui/icons-material/CancelRounded';
import HoverPreviewImage from './HoverPreviewImage';

function ResultFocusCard({ title, product, accent, showMedia }) {
  return (
    <article className={`result-focus-card ${accent}`}>
      <span className="result-focus-card__label">{title}</span>
      {showMedia && (
        <div className="result-focus-card__media">
          {product.image_url ? (
            <img src={product.image_url} alt={product.title} loading="lazy" />
          ) : (
            <div className="result-focus-card__fallback">No image</div>
          )}
        </div>
      )}
      <strong>{product.title}</strong>
      <p>{product.subtitle || product.vendor || 'Unknown'}</p>
    </article>
  );
}

export default function RoundResultPanel({ result, categoryCopy = {}, mode = 'visual', onNext, loadingNext }) {
  if (!result) return null;

  const isMatch = result.preference_match;
  const singular = categoryCopy.item_singular || 'item';
  const showMedia = mode !== 'feature';
  const hiddenPatternDetected = Boolean(result.hidden_preference_detected);
  const outcomeTitle = isMatch ? 'Preference Match!' : 'Not a match yet';
  const outcomeCopy = isMatch
    ? `Your ${singular} landed in the AI's top 5.`
    : `Your ${singular} missed the AI's top 5.`;

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
        <ResultFocusCard title={`Your ${singular}`} product={result.human_pick} accent="human" showMedia={showMedia} />
        <ResultFocusCard title="AI's top pick" product={result.ai_pick} accent="ai" showMedia={showMedia} />
      </div>

      <div className="panel">
        <div className="result-panel__header">
          <div>
            <p className="eyebrow">AI's top 5 picks</p>
            <h3>What the model expected</h3>
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
              <li key={candidate.id} className={`result-top-list__item ${matched ? 'matched' : ''} ${showMedia ? '' : 'no-media'}`}>
                <div className="result-top-list__rank">#{index + 1}</div>
                {showMedia && (
                  <div className="result-top-list__media">
                    <HoverPreviewImage
                      src={candidate.image_url}
                      alt={candidate.title}
                      fallbackClassName="result-top-list__fallback"
                    />
                  </div>
                )}
                <div className="result-top-list__body">
                  <strong>{candidate.title}</strong>
                  {!showMedia && <span>{candidate.subtitle || candidate.vendor || 'Unknown'}</span>}
                  {!showMedia && (
                    <div className="tag-list">
                      {(candidate.predicted_match_features || []).slice(0, 5).map((feature) => (
                        <span key={feature}>{feature}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="result-top-list__meta">
                  <span className="result-top-list__score-label">AI match score</span>
                  <strong>{candidate.score.toFixed(2)}</strong>
                  {matched && <CheckCircleRoundedIcon fontSize="small" />}
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {hiddenPatternDetected && (
        <div className="panel">
          <p className="eyebrow">Hidden preference detected</p>
          <h3>Sequential pattern the model noticed</h3>
          <div className="result-diagnostics">
            {result.ai_explanation.hidden_preference_hints?.map((hint) => (
              <p key={hint}>{hint}</p>
            ))}
          </div>
          <div className="result-pill-group">
            {result.ai_explanation.hidden_preferences.slice(0, 5).map(([name]) => (
              <span key={name} className="feature-tag hidden">{name}</span>
            ))}
          </div>
        </div>
      )}

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
