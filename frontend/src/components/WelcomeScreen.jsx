function CategoryCard({ category, active, disabled, onSelect }) {
  return (
    <button
      type="button"
      className={`category-card ${active ? 'active' : ''}`}
      onClick={() => onSelect(category.id)}
      disabled={disabled}
    >
      <div className="category-card__header">
        <span className="category-card__title">{category.display_name}</span>
        <span className={`category-card__availability ${disabled ? 'pending' : 'ready'}`}>
          {disabled ? 'Loading' : 'Ready'}
        </span>
      </div>
      <strong className="category-card__count">{category.available_count}</strong>
      <span className="category-card__copy">available {category.item_plural}</span>
    </button>
  );
}

export default function WelcomeScreen({
  logoSrc,
  playerName,
  setPlayerName,
  accountDisplayName = '',
  isAuthenticated = false,
  categories = [],
  selectedCategory,
  setSelectedCategory,
  personas = [],
  selectedPersonaId = '',
  setSelectedPersonaId,
  onStart,
  onStartFresh,
  loading,
  resumable = null,
  resumeLoading = false,
  categoriesLoading = false,
  categoryLoadError = '',
  categoryProgress = 0,
  readyCategoryCount = 0,
  leaderboard = [],
  onViewPlayer,
}) {
  const activeCategory = categories.find((entry) => entry.id === selectedCategory);
  const categoryPersonas = personas.filter((entry) => entry.category === selectedCategory);
  const activePersona = categoryPersonas.find((entry) => entry.id === selectedPersonaId) || null;
  const personaSelected = Boolean(activePersona);
  const readyCount = categories.filter((entry) => entry.available_count >= 100).length;
  const showDatasetLoading = categoriesLoading || readyCount < categories.length;

  return (
    <section className="screen shell welcome-screen">
      <div className="welcome-layout">
        <div className="welcome-hero">
          <img src={logoSrc} alt="Recommendle" className="welcome-hero__logo" />
          <h1>Can you train an AI to choose for you?</h1>
          <p className="welcome-hero__subtitle">
            Build a taste profile and see how fast the AI can match you five rounds in a row.
          </p>

          <div className="welcome-steps">
            <article className="welcome-step">
              <span>1</span>
              <div>
                <strong>Choose 1 to 10 items</strong>
                <p>Pick from 100.</p>
              </div>
            </article>
            <article className="welcome-step">
              <span>2</span>
              <div>
                <strong>How do you feel about your set?</strong>
                <p>Rate the signal.</p>
              </div>
            </article>
            <article className="welcome-step">
              <span>3</span>
              <div>
                <strong>Build a streak of matches</strong>
                <p>Reach five in a row.</p>
              </div>
            </article>
          </div>
        </div>

        <div className="panel welcome-panel">
          <div className="welcome-panel__block">
            <label className="welcome-panel__label" htmlFor="player-name">
              {isAuthenticated ? 'Display name' : 'Player name'}
            </label>
            <input
              id="player-name"
              value={playerName}
              onChange={(event) => setPlayerName(event.target.value)}
              placeholder={isAuthenticated ? (accountDisplayName || 'Your account display name') : 'How should we label this run?'}
              maxLength={80}
              disabled={loading || isAuthenticated}
            />
            {isAuthenticated ? (
              <p className="welcome-panel__hint">Runs are tied to your account display name.</p>
            ) : null}
          </div>

          <div className="welcome-panel__block">
            <div className="welcome-panel__heading">
              <div>
                <p className="eyebrow">Choose a category</p>
                <h2>Pick a category</h2>
              </div>
              <span className="welcome-panel__count">
                {activeCategory?.display_name || 'Select one'}
              </span>
            </div>
            <div className="category-card-grid">
              {categories.map((category) => (
                <CategoryCard
                  key={category.id}
                  category={category}
                  active={category.id === selectedCategory}
                  disabled={category.available_count < 100}
                  onSelect={setSelectedCategory}
                />
              ))}
            </div>
          </div>

          <div className="welcome-panel__block">
            <div className="welcome-panel__heading">
              <div>
                <p className="eyebrow">Optional shortcut</p>
                <h2>Start from a persona</h2>
              </div>
              <span className="welcome-panel__count">
                {activePersona?.display_name || 'Custom onboarding'}
              </span>
            </div>
            <div className="persona-start-grid">
              <button
                type="button"
                className={`persona-start-card ${selectedPersonaId ? '' : 'active'}`}
                onClick={() => setSelectedPersonaId('')}
              >
                <strong>Custom onboarding</strong>
                <p>Start from scratch, seed preferences if you want, and build your own onboarding set.</p>
              </button>
              {categoryPersonas.map((persona) => (
                <button
                  key={persona.id}
                  type="button"
                  className={`persona-start-card ${selectedPersonaId === persona.id ? 'active' : ''}`}
                  onClick={() => setSelectedPersonaId(persona.id)}
                >
                  <strong>{persona.display_name}</strong>
                  <p>{persona.summary}</p>
                  <span className="persona-start-card__meta">
                    Completed in {persona.rounds_to_complete || 0} rounds
                  </span>
                </button>
              ))}
            </div>
            <p className="welcome-panel__hint">
              Choose a persona to skip onboarding and continue from an admin-prepared completed profile.
            </p>
          </div>

          {showDatasetLoading && (
            <div className="dataset-loading" role="status" aria-live="polite">
              <div className="dataset-loading__header">
                <span>{categoriesLoading ? 'Loading datasets...' : 'Preparing every category for the 100-item onboarding pool'}</span>
                <strong>{Math.round(categoryProgress)}%</strong>
              </div>
              <div className="dataset-loading__track">
                <div className="dataset-loading__fill" style={{ width: `${Math.max(8, categoryProgress)}%` }} />
              </div>
              <p className="dataset-loading__copy">
                Ready categories: {readyCategoryCount}/{categories.length || 0}
              </p>
              {categoryLoadError && <p className="dataset-loading__error">Backend is still warming up. Retrying automatically.</p>}
            </div>
          )}

          <div className="welcome-panel__cta">
            <button
              type="button"
              onClick={onStart}
              disabled={loading || categoriesLoading || resumeLoading || !playerName.trim() || !activeCategory}
            >
              {loading ? 'Starting...' : personaSelected ? `Start Fresh As ${activePersona.display_name}` : resumable?.exists ? 'Continue run' : 'Start training'}
            </button>
            <button
              type="button"
              className="secondary-btn"
              onClick={onStartFresh}
              disabled={personaSelected || loading || categoriesLoading || resumeLoading || !playerName.trim() || !resumable?.can_start_fresh}
            >
              {personaSelected ? 'Persona Selected' : 'Start fresh'}
            </button>
          </div>

          {resumable?.exists && (
            <div className="welcome-panel__resume">
              <strong>Resume ready</strong>
              <p>
                {personaSelected
                  ? 'A persona is selected, so the main button will start a new fresh run from that persona.'
                  : `Continue from round ${(resumable.current_round || 0) + 1}.`}
              </p>
            </div>
          )}
        </div>
      </div>

      <div className="panel leaderboard-panel welcome-leaderboard">
        <div className="leaderboard-panel__header">
          <div>
            <p className="eyebrow">Co-op leaderboard</p>
            <h3>Fastest completed runs</h3>
          </div>
          <span>{activeCategory?.display_name || 'Category'}</span>
        </div>
        {leaderboard.length === 0 ? (
          <p className="muted">No completed runs yet for this category.</p>
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
                  title={`View ${entry.player_name}'s run history`}
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
    </section>
  );
}
