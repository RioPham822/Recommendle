const RATING_GUIDE = [
  { value: 1, title: 'Off target', description: 'This set feels scattered. The AI should treat it as a weak starting signal.' },
  { value: 2, title: 'Loose fit', description: 'A few items belong, but the set still feels noisy.' },
  { value: 3, title: 'Mixed', description: 'This is a decent snapshot of your taste, with some compromises.' },
  { value: 4, title: 'Strong signal', description: 'Most of this set feels like you.' },
  { value: 5, title: 'Exactly right', description: 'This set nails your taste and should strongly guide the AI.' },
];

export default function SetRatingModal({
  open,
  rating,
  setRating,
  loading,
  onClose,
  onSubmit,
  categoryCopy = {},
}) {
  if (!open) return null;

  const plural = categoryCopy.item_plural || 'items';

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="How do you feel about your set?">
      <div className="modal-card rating-modal">
        <h3>How do you feel about your set?</h3>
        <p className="rating-modal__copy">
          This tells the AI how strongly it should trust your opening 10 {plural}.
        </p>

        <div className="rating-scale">
          {RATING_GUIDE.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`rating-choice ${rating === option.value ? 'active' : ''}`}
              onClick={() => setRating(option.value)}
              disabled={loading}
            >
              <span className="rating-choice__value">{option.value}</span>
              <strong>{option.title}</strong>
              <p>{option.description}</p>
            </button>
          ))}
        </div>

        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose} disabled={loading}>
            Back
          </button>
          <button type="button" onClick={onSubmit} disabled={loading}>
            {loading ? 'Saving...' : 'Start round 1'}
          </button>
        </div>
      </div>
    </div>
  );
}
