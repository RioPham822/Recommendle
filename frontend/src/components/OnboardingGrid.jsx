import React from 'react';
import ProductCard from './ProductCard';

export default function OnboardingGrid({
  products,
  selectedIds,
  onToggle,
  onOpenRating,
  onHome,
  mode,
  displaySchema = {},
  categoryCopy = {},
}) {
  const plural = categoryCopy.item_plural || 'products';

  return (
    <section className="screen shell">
      <header className="section-header">
        <div>
          <p className="eyebrow">Onboarding</p>
          <h2>Choose 10 from 50 {plural}</h2>
        </div>
        <div className="counter-block">
          <span>{selectedIds.length}/10 selected</span>
          <button
            type="button"
            className="ghost"
            onClick={onHome}
          >
            Home
          </button>
          <button
            type="button"
            onClick={onOpenRating}
            disabled={selectedIds.length !== 10}
          >
            Continue
          </button>
        </div>
      </header>

      <div className="pool-grid">
        {products.map((product) => (
          <ProductCard
            key={product.id}
            product={product}
            mode={mode}
            displaySchema={displaySchema}
            selected={selectedIds.includes(product.id)}
            onClick={() => onToggle(product.id)}
          />
        ))}
      </div>
    </section>
  );
}
