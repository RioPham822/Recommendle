import React from 'react';
import { formatPrice } from '../lib/api';

function getDisplayValue(product, key) {
  if (key === 'price') {
    return formatPrice(product.price_min, product.price_max);
  }
  if (key === 'nib_size') {
    const nibs = product.attributes?.options?.['Nib Size'];
    return Array.isArray(nibs) && nibs.length > 0 ? nibs[0] : null;
  }
  if (key === 'nib_sizes') {
    const nibs = product.attributes?.options?.['Nib Size'];
    return Array.isArray(nibs) ? nibs : [];
  }
  return product[key] ?? product.attributes?.[key] ?? null;
}

function formatFieldValue(value, type) {
  if (value === null || value === undefined || value === '') return '';
  if (type === 'list') {
    if (!Array.isArray(value)) return String(value);
    return value.slice(0, 3).join(', ');
  }
  if (type === 'number') {
    if (typeof value !== 'number') return String(value);
    return Number.isInteger(value) ? String(value) : value.toFixed(1);
  }
  if (type === 'long_text') {
    const text = String(value);
    return text.length > 220 ? `${text.slice(0, 220)}...` : text;
  }
  if (type === 'link') {
    return String(value);
  }
  return String(value);
}

export default function ProductCard({
  product,
  mode,
  displaySchema = {},
  selected,
  onClick,
  hoverPanelSide = null,
  compact = false,
}) {
  const cardFields = Array.isArray(displaySchema.card_fields) ? displaySchema.card_fields : [];
  const detailFields = Array.isArray(displaySchema.detail_fields) ? displaySchema.detail_fields : [];
  const detailRows = detailFields
    .map((field) => {
      const value = getDisplayValue(product, field.key);
      return {
        key: field.key,
        label: field.label || field.key,
        type: field.type || 'text',
        value,
        formatted: formatFieldValue(value, field.type || 'text'),
      };
    })
    .filter((row) => {
      if (row.type === 'list') return Array.isArray(row.value) ? row.value.length > 0 : Boolean(row.formatted);
      return Boolean(row.formatted);
    });

  const featureTokens = [...(product.meta_badges || []), ...(product.tags || []).slice(0, 4)].slice(0, 6);

  return (
    <button
      type="button"
      className={`product-card mode-${mode} ${selected ? 'selected' : ''} ${compact ? 'compact' : ''} ${hoverPanelSide ? `hover-panel-${hoverPanelSide}` : ''}`}
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

        {mode === 'visual' && cardFields.length > 0 && (
          <div className="feature-list card-feature-list">
            {cardFields.map((field) => {
              const value = getDisplayValue(product, field.key);
              const formatted = formatFieldValue(value, field.type || 'text');
              if (!formatted) return null;
              return (
                <p key={field.key}>
                  <strong>{field.label || field.key}</strong>: {formatted}
                </p>
              );
            })}
          </div>
        )}

        {mode === 'visual' && featureTokens.length > 0 && (
          <div className="tag-list">
            {featureTokens.map((token) => (
              <span key={token}>{token}</span>
            ))}
          </div>
        )}

        {mode === 'feature' && detailRows.length > 0 && (
          <div className="feature-list">
            {detailRows.map((row) => (
              <p key={row.key}>
                <strong>{row.label}</strong>: {row.formatted}
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

        {detailRows.length > 0 && (
          <div className="card-hover-detail">
            {detailRows.map((row) => (
              <p key={row.key}>
                <strong>{row.label}</strong>: {row.formatted}
              </p>
            ))}
          </div>
        )}
      </div>
    </button>
  );
}
