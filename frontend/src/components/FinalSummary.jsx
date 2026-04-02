import { useEffect, useState } from 'react';
import CheckCircleRoundedIcon from '@mui/icons-material/CheckCircleRounded';
import { getGameSummary } from '../lib/api';
import HoverPreviewImage from './HoverPreviewImage';

function MiniBarChart({ data, label, className = '' }) {
  if (!data.length) {
    return (
      <div className={`panel mini-chart ${className}`}>
        <div className="mini-chart__header">
          <h4>{label}</h4>
        </div>
        <p className="muted">No data yet.</p>
      </div>
    );
  }

  const max = Math.max(...data.map((item) => item.value), 1);

  return (
    <div className={`panel mini-chart ${className}`}>
      <div className="mini-chart__header">
        <h4>{label}</h4>
      </div>
      <div className="chart-bars">
        {data.map((item) => (
          <div key={item.label} className="chart-bar-col">
            <div className="chart-bar-track">
              <div
                className={`chart-bar ${item.highlight ? 'highlight' : ''}`}
                style={{ height: `${item.value > 0 ? Math.max((item.value / max) * 100, 10) : 8}%` }}
              />
            </div>
            <span className="chart-bar-value">{item.value}</span>
            <span className="chart-bar-label">{item.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function FinalSummary({
  playerName,
  category,
  gameId,
  leaderboard,
  onRestart,
  onViewPlayer,
}) {
  const [summary, setSummary] = useState(null);
  const [loadError, setLoadError] = useState('');

  useEffect(() => {
    if (!gameId) return;
    getGameSummary(gameId)
      .then(setSummary)
      .catch((err) => setLoadError(err.message || 'Could not load summary.'));
  }, [gameId]);

  const copy = summary?.category_copy || {};
  const topLabel = copy.top_recommendations_label || "AI's Top 5 Picks";
  const hiddenLabel = copy.hidden_gems_label || 'Hidden Gems';
  const roundsData = summary?.round_stats?.map((round) => ({
    label: `R${round.round_number}`,
    value: round.preference_match ? 1 : 0,
    highlight: round.preference_match,
  })) || [];
  const streakData = summary?.round_stats?.map((round) => ({
    label: `R${round.round_number}`,
    value: round.current_match_streak || 0,
    highlight: true,
  })) || [];

  return (
    <section className="screen shell final-summary">
      <div className="panel final-summary__hero">
        <div>
          <p className="eyebrow">Run complete</p>
          <h2>AI learned {playerName}&apos;s taste</h2>
          <p>
            The model reached {summary?.match_streak_target || 5} preference matches in a row and finished the run in{' '}
            <strong>{summary?.rounds_played || 0} rounds</strong>.
          </p>
        </div>
        <div className="final-summary__hero-icon">
          <CheckCircleRoundedIcon fontSize="large" />
        </div>
      </div>

      {summary && (
        <div className="stats-row">
          <div className="stat-card">
            <span className="stat-value">{summary.rounds_played}</span>
            <span className="stat-label">Rounds to completion</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{summary.longest_match_streak}</span>
            <span className="stat-label">Longest streak</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{Math.round((summary.match_rate || 0) * 100)}%</span>
            <span className="stat-label">Overall match rate</span>
          </div>
        </div>
      )}

      {summary && (
        <div className="charts-row">
          <MiniBarChart data={roundsData} label="Preference match by round" />
          <MiniBarChart data={streakData} label="Streak progression" className="mini-chart--streak" />
        </div>
      )}

      {summary && (
        <div className="final-summary__insights">
          <div className="panel">
            <p className="eyebrow">What the AI learned</p>
            <h3>Preference signals</h3>
            <div className="result-pill-group">
              {summary.learned_preferences.map(([name]) => (
                <span key={name} className="feature-tag positive">{name}</span>
              ))}
            </div>
            {summary.learned_dislikes?.length > 0 && (
              <>
                <p className="eyebrow" style={{ marginTop: '1rem' }}>What it moved away from</p>
                <div className="result-pill-group">
                  {summary.learned_dislikes.map(([name]) => (
                    <span key={name} className="feature-tag negative">{name}</span>
                  ))}
                </div>
              </>
            )}
          </div>

          <div className="panel">
            <p className="eyebrow">{topLabel}</p>
            <h3>Recommendations</h3>
            <ul className="recommendation-list">
              {summary.top5_recommendations.map((recommendation, index) => (
                <li key={recommendation.id}>
                  <span>#{index + 1}</span>
                  <div className="recommendation-list__media">
                    <HoverPreviewImage
                      src={recommendation.image_url}
                      alt={recommendation.title}
                      fallbackClassName="result-top-list__fallback"
                      previewPlacement="top"
                    />
                  </div>
                  <div className="recommendation-list__body">
                    <strong>{recommendation.title}</strong>
                    <p>{recommendation.subtitle || recommendation.vendor || category}</p>
                  </div>
                  <div className="recommendation-list__meta">
                    <span className="result-top-list__score-label">AI match score</span>
                    <strong>{recommendation.score?.toFixed(2) ?? 'N/A'}</strong>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {summary?.hidden_preferences?.length > 0 && (
        <div className="panel">
          <p className="eyebrow">{hiddenLabel}</p>
          <h3>Hidden-gem insight</h3>
          {summary.hidden_gems_explanation && <p className="muted">{summary.hidden_gems_explanation}</p>}
          <div className="result-pill-group">
            {summary.hidden_preferences.map(([name]) => (
              <span key={name} className="feature-tag hidden">{name}</span>
            ))}
          </div>
          {summary.hidden_gems_products?.length > 0 && (
            <ul className="recommendation-list recommendation-list--secondary">
              {summary.hidden_gems_products.map((recommendation, index) => (
                <li key={recommendation.id}>
                  <span>#{index + 1}</span>
                  <div className="recommendation-list__media">
                    <HoverPreviewImage
                      src={recommendation.image_url}
                      alt={recommendation.title}
                      fallbackClassName="result-top-list__fallback"
                      previewPlacement="top"
                    />
                  </div>
                  <div className="recommendation-list__body">
                    <strong>{recommendation.title}</strong>
                    <p>{recommendation.subtitle || recommendation.vendor || category}</p>
                  </div>
                  <div className="recommendation-list__meta">
                    <span className="result-top-list__score-label">Hidden gem score</span>
                    <strong>{recommendation.score?.toFixed(2) ?? 'N/A'}</strong>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {loadError && <p className="muted">{loadError}</p>}

      <div className="panel leaderboard-panel">
        <div className="leaderboard-panel__header">
          <div>
            <p className="eyebrow">Co-op leaderboard</p>
            <h3>Fastest completed runs</h3>
          </div>
          <span>{copy.display_name || category}</span>
        </div>
        {leaderboard.length === 0 ? (
          <p className="muted">No completed runs yet.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Rank</th>
                <th>Player</th>
                <th>Rounds</th>
                <th>Match Rate</th>
                <th>Best Streak</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((entry) => (
                <tr
                  key={`${entry.player_name}-${entry.created_at}`}
                  className="leaderboard-row-clickable"
                  onClick={() => onViewPlayer && onViewPlayer(entry.player_name)}
                >
                  <td>{entry.rank}</td>
                  <td className="player-name-cell">{entry.player_name}</td>
                  <td>{entry.rounds_to_complete || entry.rounds_completed}</td>
                  <td>{Math.round((entry.match_rate || 0) * 100)}%</td>
                  <td>{entry.longest_match_streak || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="round-actions round-actions--end">
        <button type="button" onClick={onRestart}>Start another run</button>
      </div>
    </section>
  );
}
