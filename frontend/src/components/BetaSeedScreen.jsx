import { useEffect, useMemo, useState } from 'react';
import { searchProducts } from '../lib/api';

export default function BetaSeedScreen({ category, onSkip, onSubmit, loading }) {
  const [likes, setLikes] = useState([]);
  const [dislikes, setDislikes] = useState([]);
  const [likeMovies, setLikeMovies] = useState([]);
  const [dislikeMovies, setDislikeMovies] = useState([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const [target, setTarget] = useState('like');
  const maxSelections = 5;

  const config = useMemo(() => {
    if (category === 'movies') {
      return {
        field: 'genres',
        label: 'genres',
        options: ['Drama', 'Comedy', 'Action', 'Sci-Fi', 'Thriller', 'Romance', 'Horror', 'Adventure', 'Fantasy', 'Animation', 'Mystery', 'Crime'],
      };
    }
    if (category === 'games') {
      return {
        field: 'genres',
        label: 'genres',
        options: ['RPG', 'Action', 'Strategy', 'Adventure', 'Shooter', 'Indie', 'Simulation', 'Sports', 'Racing', 'Puzzle', 'Platformer', 'Fighting'],
      };
    }
    return {
      field: 'tags',
      label: 'tags',
      options: ['Minimalist', 'Luxury', 'Vintage', 'Modern', 'Bold Colors', 'Pastel', 'Travel', 'Pocket', 'Classic', 'Premium', 'Lightweight', 'Signature'],
    };
  }, [category]);

  const toggleSelection = (value, list, setter, otherList, otherSetter) => {
    if (list.includes(value)) {
      setter(list.filter((item) => item !== value));
      return;
    }
    if (list.length >= maxSelections) return;
    if (otherList.includes(value)) {
      otherSetter(otherList.filter((item) => item !== value));
    }
    setter([...list, value]);
  };

  const handleSubmit = () => {
    const payload = {
      likes: likes.length ? { [config.field]: likes } : {},
      dislikes: dislikes.length ? { [config.field]: dislikes } : {},
      like_product_ids: likeMovies.map((movie) => movie.id),
      dislike_product_ids: dislikeMovies.map((movie) => movie.id),
    };
    onSubmit(payload);
  };

  useEffect(() => {
    let timerId;
    const term = query.trim();
    if (term.length < 2) {
      setResults([]);
      setSearchError('');
      setSearching(false);
      return undefined;
    }
    timerId = window.setTimeout(async () => {
      setSearching(true);
      setSearchError('');
      try {
        const data = await searchProducts(term, category, 10, true);
        setResults(Array.isArray(data) ? data : []);
      } catch (err) {
        setSearchError(err.message || 'Search failed.');
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 250);
    return () => {
      if (timerId) window.clearTimeout(timerId);
    };
  }, [query, category]);

  const addMovie = (movie) => {
    if (target === 'like') {
      if (likeMovies.some((m) => m.id === movie.id)) return;
      setLikeMovies((prev) => [...prev, movie].slice(0, 5));
      setDislikeMovies((prev) => prev.filter((m) => m.id !== movie.id));
    } else {
      if (dislikeMovies.some((m) => m.id === movie.id)) return;
      setDislikeMovies((prev) => [...prev, movie].slice(0, 5));
      setLikeMovies((prev) => prev.filter((m) => m.id !== movie.id));
    }
  };

  const removeMovie = (movieId, list, setter) => {
    setter(list.filter((m) => m.id !== movieId));
  };

  return (
    <section className="screen shell seed-screen">
      <header className="section-header">
        <div>
          <p className="eyebrow">Beta Setup</p>
          <h2>Tell us a little about your taste</h2>
        </div>
        <button type="button" className="ghost" onClick={onSkip} disabled={loading}>
          Skip
        </button>
      </header>

      <div className="panel seed-panel">
        <p className="seed-copy">
          Pick up to {maxSelections} {config.label} you love and want less of. This helps the AI personalize the onboarding pool.
        </p>

        <div className="seed-group">
          <label>I like...</label>
          <div className="seed-options">
            {config.options.map((option) => (
              <button
                key={`like-${option}`}
                type="button"
                className={`seed-chip ${likes.includes(option) ? 'selected' : ''}`}
                onClick={() => toggleSelection(option, likes, setLikes, dislikes, setDislikes)}
                disabled={loading}
              >
                {option}
              </button>
            ))}
          </div>
          <p className="seed-help">Selected: {likes.length}/{maxSelections}</p>
        </div>

        <div className="seed-group">
          <label>I want less of...</label>
          <div className="seed-options">
            {config.options.map((option) => (
              <button
                key={`less-${option}`}
                type="button"
                className={`seed-chip ${dislikes.includes(option) ? 'selected' : ''}`}
                onClick={() => toggleSelection(option, dislikes, setDislikes, likes, setLikes)}
                disabled={loading}
              >
                {option}
              </button>
            ))}
          </div>
          <p className="seed-help">Selected: {dislikes.length}/{maxSelections}</p>
        </div>

        <div className="seed-group">
          <label>Search and add specific titles</label>
          <div className="seed-search">
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search titles (fuzzy search enabled)"
              disabled={loading}
            />
          </div>
          {searching && <p className="seed-help">Searching...</p>}
          <div className="seed-target">
            <button
              type="button"
              className={`seed-chip ${target === 'like' ? 'selected' : ''}`}
              onClick={() => setTarget('like')}
              disabled={loading}
            >
              Add to Likes
            </button>
            <button
              type="button"
              className={`seed-chip ${target === 'dislike' ? 'selected' : ''}`}
              onClick={() => setTarget('dislike')}
              disabled={loading}
            >
              Add to Less of
            </button>
          </div>
          {searchError && <p className="seed-help">{searchError}</p>}
          <div className="seed-results">
            {results.map((movie) => (
              <button
                key={movie.id}
                type="button"
                className="seed-result"
                onClick={() => addMovie(movie)}
                disabled={loading}
              >
                <div className="seed-result-main">
                  <span className="seed-result-title">{movie.title}</span>
                  <span className="seed-result-meta">
                    {movie.data?.release_year ? `${movie.data.release_year}` : ''}
                    {movie.data?.directors?.length ? ` · Dir. ${movie.data.directors[0]}` : ''}
                    {movie.data?.genres?.length ? ` · ${movie.data.genres.slice(0, 2).join(', ')}` : ''}
                  </span>
                </div>
                <div className="seed-result-preview">
                  <div className="seed-preview-media">
                    {movie.data?.images?.[0]?.url ? (
                      <img src={movie.data.images[0].url} alt={movie.title} loading="lazy" />
                    ) : (
                      <div className="seed-preview-noimg">No image</div>
                    )}
                  </div>
                  <div className="seed-preview-body">
                    <p className="seed-preview-title">{movie.title}</p>
                    <p className="seed-preview-subtitle">{movie.data?.directors?.[0] ? `Dir. ${movie.data.directors[0]}` : (movie.vendor || 'Unknown')}</p>
                    <div className="seed-preview-tags">
                      {[...(movie.data?.genres || []).slice(0, 4)].map((tag) => (
                        <span key={tag}>{tag}</span>
                      ))}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>

          {(likeMovies.length > 0 || dislikeMovies.length > 0) && (
            <div className="seed-selected">
              {likeMovies.length > 0 && (
                <div>
                  <p className="seed-help">Liked titles</p>
                  <div className="seed-selected-list">
                    {likeMovies.map((movie) => (
                      <button
                        key={`liked-${movie.id}`}
                        type="button"
                        className="seed-chip selected"
                        onClick={() => removeMovie(movie.id, likeMovies, setLikeMovies)}
                        disabled={loading}
                      >
                        {movie.title}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              {dislikeMovies.length > 0 && (
                <div>
                  <p className="seed-help">Less of</p>
                  <div className="seed-selected-list">
                    {dislikeMovies.map((movie) => (
                      <button
                        key={`disliked-${movie.id}`}
                        type="button"
                        className="seed-chip"
                        onClick={() => removeMovie(movie.id, dislikeMovies, setDislikeMovies)}
                        disabled={loading}
                      >
                        {movie.title}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="round-actions">
        <button type="button" className="ghost" onClick={onSkip} disabled={loading}>
          Skip for now
        </button>
        <button type="button" onClick={handleSubmit} disabled={loading}>
          {loading ? 'Saving...' : 'Continue'}
        </button>
      </div>
    </section>
  );
}
