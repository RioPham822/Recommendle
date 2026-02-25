import React from 'react';

export default function SetRatingModal({
  open,
  rating,
  setRating,
  loading,
  onClose,
  onSubmit,
  categoryCopy = {},
}) {
  if (!open) {
    return null;
  }

  const plural = categoryCopy.item_plural || 'products';

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Set rating">
      <div className="modal-card">
        <h3>Rate Your Initial Set</h3>
        <p>How coherent does your selected set of 10 {plural} feel?</p>

        <div className="rating-control">
          <input
            type="range"
            min="1"
            max="5"
            value={rating}
            onChange={(event) => setRating(Number(event.target.value))}
            disabled={loading}
          />
          <strong>{rating}/5</strong>
        </div>

        <div className="modal-actions">
          <button type="button" className="ghost" onClick={onClose} disabled={loading}>
            Back
          </button>
          <button type="button" onClick={onSubmit} disabled={loading}>
            {loading ? 'Submitting...' : 'Submit & Start Round 1'}
          </button>
        </div>
      </div>
    </div>
  );
}
