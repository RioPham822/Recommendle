import { useEffect, useState } from 'react';
import { getGameSummary, getPlayerHistory } from '../lib/api';

export default function PlayerStatsModal({ playerName, category = 'fountain_pens', onClose }) {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [expandedGameId, setExpandedGameId] = useState(null);
  const [gameSummary, setGameSummary] = useState(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState('');

  useEffect(() => {
    if (!playerName) return;
    setLoading(true);
    getPlayerHistory(playerName, category)
      .then(setGames)
      .catch((err) => setError(err.message || 'Could not load history.'))
      .finally(() => setLoading(false));
  }, [playerName, category]);

  async function handleExpandGame(gameId) {
    if (expandedGameId === gameId) {
      setExpandedGameId(null);
      setGameSummary(null);
      setSummaryError('');
      return;
    }
    setExpandedGameId(gameId);
    setSummaryLoading(true);
    setSummaryError('');
    try {
      const summary = await getGameSummary(gameId);
      setGameSummary(summary);
    } catch (err) {
      setGameSummary(null);
      setSummaryError(err.message || 'Could not load game details.');
    } finally {
      setSummaryLoading(false);
    }
  }

  const redesignedGames = games.filter((game) => (game.schema_version || 2) >= 3);
  const totalGames = games.length;
  const avgRoundsToComplete = redesignedGames.length
    ? Math.round(redesignedGames.reduce((sum, game) => sum + (game.rounds_to_complete || 0), 0) / redesignedGames.length)
    : 0;
  const avgMatchRate = redesignedGames.length
    ? Math.round((redesignedGames.reduce((sum, game) => sum + (game.match_rate || 0), 0) / redesignedGames.length) * 100)
    : 0;
  const bestStreak = redesignedGames.length
    ? Math.max(...redesignedGames.map((game) => game.longest_match_streak || 0))
    : 0;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="player-stats-card" onClick={(event) => event.stopPropagation()}>
        <div className="player-stats-header">
          <div>
            <p className="eyebrow">Player profile</p>
            <h2>{playerName}</h2>
          </div>
          <button type="button" className="ghost close-btn" onClick={onClose}>Close</button>
        </div>

        {loading && <p className="muted">Loading...</p>}
        {error && <p className="muted">{error}</p>}

        {!loading && !error && (
          <>
            <div className="stats-row">
              <div className="stat-card">
                <span className="stat-value">{totalGames}</span>
                <span className="stat-label">Saved runs</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{avgRoundsToComplete || '-'}</span>
                <span className="stat-label">Avg rounds to finish</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{avgMatchRate || 0}%</span>
                <span className="stat-label">Avg match rate</span>
              </div>
              <div className="stat-card">
                <span className="stat-value">{bestStreak}</span>
                <span className="stat-label">Best streak</span>
              </div>
            </div>

            <div className="game-history">
              <h3>Run history</h3>
              {games.length === 0 ? (
                <p className="muted">No completed runs yet.</p>
              ) : (
                <ul className="history-list">
                  {games.map((game) => {
                    const redesigned = (game.schema_version || 2) >= 3;
                    const isExpanded = expandedGameId === game.game_id;
                    return (
                      <li key={game.game_id} className={`history-item ${isExpanded ? 'expanded' : ''}`}>
                        <button type="button" className="history-row" onClick={() => handleExpandGame(game.game_id)}>
                          <span className={`history-outcome ${redesigned ? 'win' : 'tie'}`}>
                            {redesigned ? 'Co-op' : 'Legacy'}
                          </span>
                          <span className="history-score">
                            {redesigned
                              ? `${game.rounds_to_complete || game.rounds_played} rounds`
                              : `${game.human_score} - ${game.ai_score}`}
                          </span>
                          <span className="history-accuracy">
                            {redesigned
                              ? `${Math.round((game.match_rate || 0) * 100)}% match`
                              : `${Math.round((game.ai_accuracy || 0) * 100)}% AI`}
                          </span>
                          <span className="history-date">{new Date(game.created_at).toLocaleDateString()}</span>
                        </button>

                        {isExpanded && (
                          <div className="history-detail">
                            {summaryLoading && <p className="muted">Loading run details...</p>}
                            {!summaryLoading && summaryError && <p className="muted">{summaryError}</p>}
                            {!summaryLoading && !summaryError && gameSummary && (
                              <>
                                {(gameSummary.schema_version || 2) >= 3 ? (
                                  <>
                                    <div className="detail-section">
                                      <h4>Match progression</h4>
                                      <div className="round-pills">
                                        {gameSummary.round_stats.map((round) => (
                                          <span
                                            key={round.round_number}
                                            className={`round-pill ${round.preference_match ? 'ai-won' : 'human-won'}`}
                                            title={`Round ${round.round_number}: streak ${round.current_match_streak}`}
                                          >
                                            R{round.round_number}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                    <div className="detail-section">
                                      <h4>Learned preferences</h4>
                                      <div className="tag-list">
                                        {gameSummary.learned_preferences.slice(0, 8).map(([name]) => (
                                          <span key={name} className="feature-tag positive">{name}</span>
                                        ))}
                                      </div>
                                    </div>
                                  </>
                                ) : (
                                  <div className="detail-section">
                                    <h4>Legacy score summary</h4>
                                    <p className="muted">
                                      Human {gameSummary.human_score} vs AI {gameSummary.ai_score}. This run used the previous score-based rules.
                                    </p>
                                  </div>
                                )}
                              </>
                            )}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
