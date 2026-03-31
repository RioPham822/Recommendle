import CheckRoundedIcon from '@mui/icons-material/CheckRounded';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';

export default function ProductCard({
  product,
  mode,
  selected,
  onClick,
  compact = false,
  showDismiss = false,
  dismissed = false,
  onToggleDismiss,
  selectionNumber = 0,
  showPredictionHints = false,
}) {
  const hasValue = (value) => {
    if (value === null || value === undefined) return false;
    if (typeof value === 'string') return value.trim() !== '';
    if (Array.isArray(value)) return value.length > 0;
    if (typeof value === 'object') return Object.keys(value).length > 0;
    return true;
  };

  const attributes = Object.entries(product.attributes || {})
    .filter(([, value]) => hasValue(value))
    .slice(0, compact ? 3 : 5);

  const showMedia = mode !== 'feature';
  const showSelectionBadge = selectionNumber > 0 || selected;

  function formatAttrValue(value) {
    if (Array.isArray(value)) {
      return value.slice(0, 2).join(', ');
    }
    return String(value);
  }

  const hintText = product.predicted_match_features?.slice(0, 5) || [];

  function handleCardClick(event) {
    onClick?.();
    event.currentTarget.blur();
  }

  return (
    <div
      className={[
        'product-card-shell',
        compact ? 'compact' : '',
        selected ? 'selected' : '',
        dismissed ? 'dismissed' : '',
      ].filter(Boolean).join(' ')}
    >
      <button
        type="button"
        className={`product-card mode-${mode}`}
        onClick={handleCardClick}
      >
        {showSelectionBadge && (
          <span className="product-card__selection">
            {selectionNumber > 0 ? selectionNumber : <CheckRoundedIcon fontSize="small" />}
          </span>
        )}

        {showMedia && (
          <div className="product-card__media">
            {product.image_url ? (
              <img src={product.image_url} alt={product.title} loading="lazy" />
            ) : (
              <div className="product-card__fallback">No image</div>
            )}
          </div>
        )}

        <div className="product-card__body">
          <h3>{product.title}</h3>

          {mode === 'feature' && attributes.length > 0 && (
            <div className="feature-list">
              {attributes.map(([key, value]) => (
                <p key={key}>
                  <strong>{key.replace(/_/g, ' ')}</strong>
                  <span>{formatAttrValue(value)}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      </button>

      {showDismiss && (
        <button
          type="button"
          className={`product-card__dismiss-chip ${dismissed ? 'active' : ''}`}
          onClick={onToggleDismiss}
          title={dismissed ? 'Undo less like this' : 'Tell the AI less like this'}
          aria-label={dismissed ? `Undo less like this for ${product.title}` : `Tell the AI less like this for ${product.title}`}
        >
          <CloseRoundedIcon fontSize="small" />
        </button>
      )}

      {showPredictionHints && hintText.length > 0 && (
        <div className="product-card__insights">
          <p>AI thinks you like</p>
          <ul>
            {hintText.map((feature) => (
              <li key={feature}>{feature}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
