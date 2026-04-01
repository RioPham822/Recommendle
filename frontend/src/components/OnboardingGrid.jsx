import PreferenceDeck from './PreferenceDeck';
import ProductCard from './ProductCard';

const MIN_ONBOARDING_SELECTIONS = 1;
const MAX_ONBOARDING_SELECTIONS = 10;

function flattenSeedSignals(group = {}) {
  return Object.values(group)
    .flatMap((values) => (Array.isArray(values) ? values : []))
    .filter(Boolean);
}

export default function OnboardingGrid({
  products,
  selectedIds,
  onToggle,
  onOpenRating,
  mode,
  categoryCopy = {},
  seedPreferences = null,
}) {
  const plural = categoryCopy.item_plural || 'items';
  const selectedProducts = selectedIds
    .map((id) => products.find((product) => product.id === id))
    .filter(Boolean);
  const likedSignals = flattenSeedSignals(seedPreferences?.likes);
  const dislikedSignals = flattenSeedSignals(seedPreferences?.dislikes);
  const hasSeedSignals = likedSignals.length > 0 || dislikedSignals.length > 0;

  return (
    <section className="screen shell onboarding-screen">
      <div className="onboarding-screen__header">
        <div>
          <p className="eyebrow">Onboarding</p>
          <h2>Choose 1 to 10 {plural} from 100</h2>
          <p className="muted">Pick anywhere from 1 to 10 that feel most like you.</p>
        </div>
      </div>

      {hasSeedSignals && (
        <div className="panel onboarding-signal-summary">
          <div>
            <p className="eyebrow">Quick Signals Applied</p>
            <h3>Your opening pool was biased using these signals</h3>
          </div>
          {likedSignals.length > 0 && (
            <div className="onboarding-signal-summary__group">
              <strong>More like this</strong>
              <div className="tag-list">
                {likedSignals.map((signal) => (
                  <span key={`like-${signal}`}>{signal}</span>
                ))}
              </div>
            </div>
          )}
          {dislikedSignals.length > 0 && (
            <div className="onboarding-signal-summary__group">
              <strong>Less like this</strong>
              <div className="tag-list">
                {dislikedSignals.map((signal) => (
                  <span key={`dislike-${signal}`}>{signal}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="onboarding-layout">
        <div className="onboarding-main">
          <div className="pool-grid">
            {products.map((product) => (
              <ProductCard
                key={product.id}
                product={product}
                mode={mode}
                selected={selectedIds.includes(product.id)}
                selectionNumber={selectedIds.indexOf(product.id) + 1}
                onClick={() => onToggle(product.id)}
              />
            ))}
          </div>
        </div>

        <aside className="onboarding-rail">
          <div className="panel onboarding-progress">
            <h3>Choose up to 10 items</h3>
            <div className="onboarding-progress__count">
              <strong>{selectedIds.length}</strong>
              <span>{`1-${MAX_ONBOARDING_SELECTIONS} allowed`}</span>
            </div>
            <button type="button" onClick={onOpenRating} disabled={selectedIds.length < MIN_ONBOARDING_SELECTIONS}>
              Continue
            </button>
          </div>

          <PreferenceDeck
            title="Selections so far"
            subtitle="Remove any item here at any time."
            items={selectedProducts}
            mode={mode}
            showMedia={false}
            emptyLabel="Your chosen items will appear here as you build the opening set."
            removable
            onRemove={onToggle}
            accent="warm"
          />
        </aside>
      </div>
    </section>
  );
}
