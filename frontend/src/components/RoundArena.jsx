import AutoAwesomeRoundedIcon from '@mui/icons-material/AutoAwesomeRounded';
import RefreshRoundedIcon from '@mui/icons-material/RefreshRounded';
import TrendingUpRoundedIcon from '@mui/icons-material/TrendingUpRounded';
import PreferenceDeck from './PreferenceDeck';
import ProductCard from './ProductCard';

export default function RoundArena({
  round,
  mode,
  selectedPick,
  onSelectPick,
  onSubmitPick,
  lessLikeIds = [],
  onToggleLessLike,
  onRefresh,
  refreshing = false,
  submitting,
  onRemovePreference,
  preferenceBusyId = '',
}) {
  if (!round) return null;

  const selectedProduct = round.candidates.find((candidate) => candidate.id === selectedPick) || null;
  const singular = round.category_copy?.item_singular || 'item';
  const currentMatchStreak = round.current_match_streak || 0;
  const matchTarget = round.match_streak_target || 5;

  return (
    <section className="screen shell round-screen">
      <div className="round-layout">
        <aside className="round-layout__left">
          <PreferenceDeck
            title="Your active preferences"
            subtitle="Remove anything that no longer feels right."
            items={round.preference_deck || []}
            mode={mode}
            emptyLabel="Your preference deck is still building."
            removable
            busyId={preferenceBusyId}
            onRemove={onRemovePreference}
            accent="cool"
          />
        </aside>

        <div className="round-layout__main">
          <div className="panel round-intro">
            <div className="round-intro__header">
              <div>
                <p className="eyebrow">Round {round.round_number}</p>
                <h2>{round.round_intro_title || 'Now the AI starts reading your taste.'}</h2>
              </div>
              <div className="streak-pill">
                <TrendingUpRoundedIcon fontSize="small" />
                <span>{currentMatchStreak} / {matchTarget} match streak</span>
              </div>
            </div>
            <p>{round.round_intro_body || `Pick your favorite ${singular}. If the AI places it in its top 5, your streak grows.`}</p>
          </div>

          <div className="pool-grid candidates">
            {round.candidates.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                mode={mode}
                compact
                selected={selectedPick === product.id}
                showDismiss
                dismissed={lessLikeIds.includes(product.id)}
                onToggleDismiss={() => onToggleLessLike && onToggleLessLike(product.id)}
                onClick={() => onSelectPick(product.id)}
                showPredictionHints
              />
            ))}
          </div>
        </div>

        <aside className="round-layout__right">
          <div className="panel round-sidebar">
            <p className="eyebrow">Current choice</p>
            <h3>{selectedProduct ? selectedProduct.title : `Choose a ${singular}`}</h3>
            {selectedProduct && mode !== 'feature' && (
              <div className="round-sidebar__preview">
                <div className="round-sidebar__preview-media">
                  {selectedProduct.image_url ? (
                    <img src={selectedProduct.image_url} alt={selectedProduct.title} loading="lazy" />
                  ) : (
                    <div className="round-sidebar__preview-fallback">No image</div>
                  )}
                </div>
                <div>
                  <strong>{selectedProduct.title}</strong>
                  <p>{selectedProduct.subtitle || selectedProduct.vendor || 'Unknown'}</p>
                </div>
              </div>
            )}

            <div className="round-sidebar__status">
              <div>
                <span className="round-sidebar__label">Active streak</span>
                <strong>{currentMatchStreak}</strong>
              </div>
              <div>
                <span className="round-sidebar__label">Need to win</span>
                <strong>{matchTarget - currentMatchStreak}</strong>
              </div>
            </div>

            <div className="round-sidebar__actions">
              <button
                type="button"
                className="secondary-btn"
                onClick={onRefresh}
                disabled={refreshing || submitting}
              >
                <RefreshRoundedIcon fontSize="small" />
                {refreshing ? 'Refreshing...' : 'New 10'}
              </button>
              <button
                type="button"
                onClick={onSubmitPick}
                disabled={submitting || !selectedPick}
              >
                <AutoAwesomeRoundedIcon fontSize="small" />
                {submitting ? 'Locking in...' : `Lock in ${singular}`}
              </button>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
