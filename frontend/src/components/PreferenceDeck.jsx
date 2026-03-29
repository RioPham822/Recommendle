import CloseRoundedIcon from '@mui/icons-material/CloseRounded';

export default function PreferenceDeck({
  title,
  subtitle = '',
  items = [],
  emptyLabel = 'No preferences yet.',
  removable = false,
  busyId = '',
  onRemove,
  accent = 'default',
}) {
  return (
    <section className={`panel preference-deck preference-deck--${accent}`}>
      <div className="preference-deck__header">
        <div>
          <p className="eyebrow">Preference Deck</p>
          <h3>{title}</h3>
        </div>
        <span className="preference-deck__count">{items.length}</span>
      </div>
      {subtitle && <p className="preference-deck__subtitle">{subtitle}</p>}

      {items.length === 0 ? (
        <p className="preference-deck__empty">{emptyLabel}</p>
      ) : (
        <div className="preference-deck__list">
          {items.map((item, index) => (
            <article key={item.id} className="preference-mini-card">
              <span className="preference-mini-card__index">{index + 1}</span>
              <div className="preference-mini-card__media">
                {item.image_url ? (
                  <img src={item.image_url} alt={item.title} loading="lazy" />
                ) : (
                  <div className="preference-mini-card__fallback">No image</div>
                )}
              </div>
              <div className="preference-mini-card__body">
                <strong>{item.title}</strong>
                <span>{item.subtitle || item.vendor || item.category}</span>
              </div>
              {removable && (
                <button
                  type="button"
                  className="icon-button preference-mini-card__remove"
                  onClick={() => onRemove && onRemove(item.id)}
                  aria-label={`Remove ${item.title} from your preference deck`}
                  disabled={busyId === item.id}
                  title="Remove from preference deck"
                >
                  <CloseRoundedIcon fontSize="small" />
                </button>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
