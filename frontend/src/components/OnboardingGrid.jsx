import PreferenceDeck from './PreferenceDeck';
import ProductCard from './ProductCard';

export default function OnboardingGrid({
  products,
  selectedIds,
  onToggle,
  onOpenRating,
  mode,
  categoryCopy = {},
}) {
  const plural = categoryCopy.item_plural || 'items';
  const selectedProducts = selectedIds
    .map((id) => products.find((product) => product.id === id))
    .filter(Boolean);

  return (
    <section className="screen shell onboarding-screen">
      <div className="onboarding-screen__header">
        <div>
          <p className="eyebrow">Onboarding</p>
          <h2>Choose 10 {plural} from 100</h2>
          <p className="muted">Pick the 10 that feel most like you.</p>
        </div>
      </div>

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
            <h3>Choose 10 items</h3>
            <div className="onboarding-progress__count">
              <strong>{selectedIds.length}</strong>
              <span>of 10 selected</span>
            </div>
            <button type="button" onClick={onOpenRating} disabled={selectedIds.length !== 10}>
              Continue
            </button>
          </div>

          <PreferenceDeck
            title="Selections so far"
            subtitle="Remove any item here at any time."
            items={selectedProducts}
            mode={mode}
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
