import { useState } from 'react';

const PREVIEW_MARGIN = 24;

function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export default function HoverPreviewImage({
  src,
  alt,
  fallbackText = 'No image',
  fallbackClassName = '',
  previewContent = null,
  previewPlacement = 'side',
}) {
  const [previewVisible, setPreviewVisible] = useState(false);
  const [previewStyle, setPreviewStyle] = useState(null);

  function showPreview(event) {
    if ((!src && !previewContent) || typeof window === 'undefined' || window.matchMedia('(hover: none)').matches) return;
    setPreviewVisible(true);
    if (previewPlacement === 'top') {
      setPreviewStyle(null);
      return;
    }
    const rect = event.currentTarget.getBoundingClientRect();
    const width = Math.min(window.innerWidth * 0.24, 260);
    const height = Math.min(window.innerHeight * 0.42, 320);
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    // Calculate thumbnail center
    const thumbCenterX = rect.left + rect.width / 2;
    const thumbCenterY = rect.top + rect.height / 2;

    // Determine if thumbnail is in the right half of the viewport
    const isInRightHalf = thumbCenterX > viewportWidth / 2;

    let left;
    if (isInRightHalf) {
      // Position to the left of the thumbnail with a gap
      left = rect.left - width - 16;
      // If that goes off-screen left, clamp to left margin
      left = Math.max(left, PREVIEW_MARGIN);
    } else {
      // Position to the right of the thumbnail with a gap
      left = rect.right + 16;
      // If that goes off-screen right, clamp to right edge
      if (left + width > viewportWidth - PREVIEW_MARGIN) {
        left = viewportWidth - width - PREVIEW_MARGIN;
      }
    }

    // Vertically center on thumbnail, clamped to viewport
    const top = clamp(
      thumbCenterY - height / 2,
      PREVIEW_MARGIN,
      viewportHeight - height - PREVIEW_MARGIN,
    );

    setPreviewStyle({ width, height, left, top });
  }

  function hidePreview() {
    setPreviewVisible(false);
    setPreviewStyle(null);
  }

  return (
    <div
      className="hover-preview-image"
      onMouseEnter={showPreview}
      onMouseLeave={hidePreview}
      onFocus={showPreview}
      onBlur={hidePreview}
    >
      <div className="hover-preview-image__frame">
        {src ? (
          <img src={src} alt={alt} loading="lazy" />
        ) : (
          <div className={fallbackClassName}>{fallbackText}</div>
        )}
      </div>

      {previewVisible && (previewContent || src) && (
        <div
          className={`hover-preview-image__zoom ${previewPlacement === 'top' ? 'hover-preview-image__zoom--top' : ''}`}
          style={previewPlacement === 'top' ? undefined : previewStyle}
          aria-hidden="true"
        >
          {previewContent || <img src={src} alt="" loading="lazy" />}
        </div>
      )}
    </div>
  );
}
