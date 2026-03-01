import { useEffect, useState } from 'react';
import { formatPrice, getGameSummary } from '../lib/api';

function MiniBarChart({ data, label, color }) {
  const max = Math.max(...data.map((d) => d.value), 1);
  return (
    <div className="mini-chart">
      <h4>{label}</h4>
      <div className="chart-bars">
        {data.map((d) => (
          <div key={d.label} className="chart-bar-col">
            <div
              className="chart-bar"
              style={{
                height: `${(d.value / max) * 100}%`,
                background: d.highlight ? color : 'var(--border)',
              }}
            />
            <span className="chart-bar-label">{d.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScoreChart({ roundStats }) {
  if (!roundStats || roundStats.length === 0) return null;
  const maxScore = Math.max(...roundStats.map((r) => Math.max(r.cumulative_human, r.cumulative_ai)), 10);
  const w = 280;
  const h = 120;
  const pad = 24;
  const plotW = w - pad * 2;
  const plotH = h - pad * 2;

  const pointsFor = (key) => roundStats.map((r, i) => {
    const x = pad + (i / (roundStats.length - 1 || 1)) * plotW;
    const y = pad + plotH - (r[key] / maxScore) * plotH;
    return `${x},${y}`;
  });

  return (
    <div className="mini-chart">
      <h4>Score Progression</h4>
      <svg viewBox={`0 0 ${w} ${h}`} className="line-chart">
        <line x1={pad} y1={pad} x2={pad} y2={pad + plotH} stroke="var(--border)" />
        <line x1={pad} y1={pad + plotH} x2={pad + plotW} y2={pad + plotH} stroke="var(--border)" />
        <polyline points={pointsFor('cumulative_human').join(' ')} fill="none" stroke="var(--correct)" strokeWidth="2.5" />
        <polyline points={pointsFor('cumulative_ai').join(' ')} fill="none" stroke="var(--present)" strokeWidth="2.5" />
      </svg>
    </div>
  );
}

function recMeta(rec) {
  if (rec.category === 'movies') {
    if (rec.meta_badges?.length > 0) return rec.meta_badges.join(' · ');
    return rec.subtitle || rec.vendor || 'Unknown';
  }
  return `${rec.vendor || 'Unknown'} · ${formatPrice(rec.price_min, rec.price_max)}`;
}

export default function FinalSummary({
  playerName,
  humanScore,
  aiScore,
  category,
  gameId,
  leaderboard,
  onRestart,
  onHome,
  onViewPlayer,
}) {
  const [summary, setSummary] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!gameId) return;
    getGameSummary(gameId)
      .then(setSummary)
      .catch((err) => setLoadError(err.message));
  }, [gameId]);

  const copy = summary?.category_copy || {};
  const plural = copy.item_plural || (category === 'movies' ? 'movies' : 'products');
  const topLabel = copy.top_recommendations_label || "AI's Top 5 Picks for You";
  const hiddenLabel = copy.hidden_gems_label || 'Hidden Gems - Patterns You Might Not Have Noticed';
  const hiddenSubtitle = copy.hidden_gems_subtitle || 'Items You Did Not Know You Would Love';

  const delta = humanScore - aiScore;
  let verdict = 'Tie Game';
  if (delta > 0) verdict = 'You Win!';
  if (delta < 0) verdict = 'AI Wins!';

  const roundAccuracyData = summary?.round_stats?.map((r) => ({
    label: `R${r.round_number}`,
    value: r.ai_correct ? 1 : 0,
    highlight: r.ai_correct,
  })) || [];

  const coherenceData = summary?.round_stats?.map((r) => ({
    label: `R${r.round_number}`,
    value: r.coherence,
    highlight: true,
  })) || [];

  return (
    <section className="screen shell">
      <header className="section-header" style={{ textAlign: 'center', justifyContent: 'center', flexDirection: 'column', alignItems: 'center' }}>
        <p className="eyebrow">Game Over</p>
        <h2 style={{ fontSize: 'clamp(1.6rem, 4vw, 2.4rem)' }}>{verdict}</h2>
        <p className="muted">{playerName} · Final Score: You {humanScore} - AI {aiScore}</p>
      </header>

      {summary && (
        <div className="stats-row">
          <div className="stat-card">
            <span className="stat-value">{(summary.accuracy.top3_rate * 100).toFixed(0)}%</span>
            <span className="stat-label">AI Top-3 Accuracy</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{(summary.accuracy.exact_rate * 100).toFixed(0)}%</span>
            <span className="stat-label">AI Exact Match Rate</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{summary.total_rounds}</span>
            <span className="stat-label">Rounds Played</span>
          </div>
        </div>
      )}

      {summary && (
        <div className="charts-row">
          <ScoreChart roundStats={summary.round_stats} />
          <MiniBarChart data={roundAccuracyData} label="AI Correct by Round" color="var(--correct)" />
          <MiniBarChart data={coherenceData} label="Preference Coherence" color="var(--present)" />
        </div>
      )}

      {summary && (summary.learned_preferences?.length > 0 || summary.learned_dislikes?.length > 0) && (
        <div className="panel">
          <h3>What the AI Learned About You</h3>
          {summary.learned_preferences?.length > 0 && (
            <div style={{ marginTop: '0.5rem' }}>
              <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
                You Tend to Prefer
              </h4>
              <div className="tag-list">
                {summary.learned_preferences.map(([name]) => (
                  <span key={name} className="feature-tag positive">{name}</span>
                ))}
              </div>
            </div>
          )}
          {summary.learned_dislikes?.length > 0 && (
            <div style={{ marginTop: '0.5rem' }}>
              <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--ink-faint)', marginBottom: '0.4rem' }}>
                You Tend to Avoid
              </h4>
              <div className="tag-list">
                {summary.learned_dislikes.map(([name]) => (
                  <span key={name} className="feature-tag negative">{name}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {summary?.top5_recommendations?.length > 0 && (
        <div className="panel">
          <h3>{topLabel}</h3>
          <p className="muted" style={{ marginBottom: '0.75rem' }}>
            Based on everything the model learned, these are the {plural} it thinks you would love most.
          </p>
          <ul className="rec-list">
            {summary.top5_recommendations.map((rec, i) => (
              <li key={rec.id} className="rec-item rec-item-previewable">
                <span className="rec-rank">#{i + 1}</span>
                <div className="rec-info">
                  <strong>{rec.title}</strong>
                  <span className="muted">{recMeta(rec)}</span>
                </div>
                <span className="rec-score">{rec.score.toFixed(2)}</span>
                <div className="rec-hover-preview">
                  <div className="candidate-preview-media">
                    {rec.image_url ? (
                      <img src={rec.image_url} alt={rec.title} loading="lazy" />
                    ) : (
                      <div className="candidate-preview-noimg">No image</div>
                    )}
                  </div>
                  <div className="candidate-preview-body">
                    <p className="candidate-preview-title">{rec.title}</p>
                    <p className="candidate-preview-subtitle">{rec.subtitle || rec.vendor || 'Unknown'}</p>
                    {Object.entries(rec.attributes || {}).slice(0, 4).map(([key, value]) => (
                      <p key={key} className="candidate-preview-attr">
                        <strong>{key.replace(/_/g, ' ')}</strong>: {Array.isArray(value) ? value.slice(0, 2).join(', ') : String(value)}
                      </p>
                    ))}
                    <div className="tag-list">
                      {[...(rec.meta_badges || []), ...((rec.tags || []).slice(0, 3))].map((token) => (
                        <span key={token}>{token}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {summary?.hidden_preferences?.length > 0 && (
        <div className="panel hidden-gems-panel">
          <h3>{hiddenLabel}</h3>
          {summary.hidden_gems_explanation && <p className="hidden-gems-narrative">{summary.hidden_gems_explanation}</p>}
          <div style={{ marginTop: '0.5rem' }}>
            <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--accent-hidden)', marginBottom: '0.4rem' }}>
              Hidden Preferences Detected
            </h4>
            <div className="tag-list">
              {summary.hidden_preferences.map(([name]) => (
                <span key={name} className="feature-tag hidden">{name}</span>
              ))}
            </div>
          </div>
          {summary.hidden_gems_products?.length > 0 && (
            <div style={{ marginTop: '1rem' }}>
              <h4 style={{ fontSize: '0.74rem', textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--accent-hidden)', marginBottom: '0.4rem' }}>
                {hiddenSubtitle}
              </h4>
              <ul className="rec-list">
                {summary.hidden_gems_products.map((gem, i) => (
                  <li key={gem.id} className="rec-item hidden-gem-item">
                    <span className="rec-rank gem-rank">#{i + 1}</span>
                    <div className="rec-info">
                      <strong>{gem.title}</strong>
                      <span className="muted">{recMeta(gem)}</span>
                    </div>
                    <span className="rec-score">{gem.score.toFixed(2)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {loadError && <p className="muted" style={{ textAlign: 'center' }}>Could not load game insights: {loadError}</p>}

      <div className="panel leaderboard-panel">
        <h3>Leaderboard</h3>
        {leaderboard.length === 0 ? (
          <p className="muted">No completed sessions yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Player</th>
                <th>Human</th>
                <th>AI</th>
                <th>Delta</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((entry) => (
                <tr
                  key={`${entry.player_name}-${entry.created_at}`}
                  className="leaderboard-row-clickable"
                  onClick={() => onViewPlayer && onViewPlayer(entry.player_name)}
                  title={`View ${entry.player_name}'s stats`}
                >
                  <td>{entry.rank}</td>
                  <td className="player-name-cell">{entry.player_name}</td>
                  <td>{entry.human_score}</td>
                  <td>{entry.ai_score}</td>
                  <td>{entry.score_difference >= 0 ? '+' : ''}{entry.score_difference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="round-actions" style={{ justifyContent: 'center' }}>
        <button type="button" className="ghost" onClick={onHome}>Home</button>
        <button type="button" onClick={onRestart}>Play Again</button>
      </div>
    </section>
  );
}
