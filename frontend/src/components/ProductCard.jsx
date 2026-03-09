import React from 'react';
import { formatPrice } from '../lib/api';

export default function ProductCard({ product, mode, selected, onClick, compact = false }) {
  const isMovie = product.category === 'movies';
  const hasPrice = typeof product.price_min === 'number' || typeof product.price_max === 'number';
  const hasValue = (value) => {
    if (value === null || value === undefined) return false;
    if (typeof value === 'string') return value.trim() !== '';
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === 'object') return Object.keys(value).length > 0;
    return true;
  };
  const attributes = Object.entries(product.attributes || {})
    .filter(([, value]) => hasValue(value))
    .slice(0, 5);
  const featureTokens = [...(product.meta_badges || []), ...(product.tags || []).slice(0, 4)].slice(0, 6);

  const formatAttrValue = (value) => {
    if (Array.isArray(value)) {
      return value.slice(0, 2).join(', ');
    }
    return String(value);
  };

  return (
    <button
      type="button"
      className={`product-card mode-${mode} ${selected ? 'selected' : ''} ${compact ? 'compact' : ''}`}
      onClick={onClick}
    >
      {mode === 'visual' && (
        <div className="thumb-wrap">
          {product.image_url ? (
            <img src={product.image_url} alt={product.title} loading="lazy" />
          ) : (
            <div className="image-fallback">No image</div>
          )}
        </div>
      )}

      <div className="card-content">
        <h3>{product.title}</h3>
        <p className="muted">{product.subtitle || product.vendor || 'Unknown'}</p>

        {mode === 'visual' && hasPrice && !isMovie && <p className="price">{formatPrice(product.price_min, product.price_max)}</p>}
        {mode === 'visual' && isMovie && product.meta_badges?.length > 0 && (
          <div className="tag-list">
            {product.meta_badges.map((badge) => (
              <span key={badge}>{badge}</span>
            ))}
          </div>
        )}

        {mode === 'feature' && attributes.length > 0 && (
          <div className="feature-list">
            {attributes.map(([key, value]) => (
              <p key={key}>
                <strong>{key.replace(/_/g, ' ')}</strong>: {formatAttrValue(value)}
              </p>
            ))}
          </div>
        )}

        {mode === 'feature' && featureTokens.length > 0 && (
          <div className="tag-list">
            {featureTokens.map((token) => (
              <span key={token}>{token}</span>
            ))}
          </div>
        )}
      </div>
    </button>
  );
}
