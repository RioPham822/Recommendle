import { useEffect, useMemo, useState } from 'react';
import SearchRoundedIcon from '@mui/icons-material/SearchRounded';
import { searchProducts } from '../lib/api';

function toggleToken(field, value, state, setState, opposingState, setOpposingState, maxSelections) {
  const current = state[field] || [];
  if (current.includes(value)) {
    setState((prev) => ({ ...prev, [field]: current.filter((item) => item !== value) }));
    return;
  }
  if (current.length >= maxSelections) return;
  const opposing = opposingState[field] || [];
  if (opposing.includes(value)) {
    setOpposingState((prev) => ({ ...prev, [field]: opposing.filter((item) => item !== value) }));
  }
  setState((prev) => ({ ...prev, [field]: [...(prev[field] || []), value] }));
}

function SeedSection({ title, description, sections, likes, dislikes, setLikes, setDislikes, maxSelections, loading }) {
  return (
    <div className="seed-section">
      <div className="seed-section__header">
        <h3>{title}</h3>
        <p>{description}</p>
      </div>
      <div className="seed-section__groups">
        {sections.map((section) => (
          <article key={section.field} className="seed-card">
            <div className="seed-card__head">
              <strong>{section.label}</strong>
              <span>Up to {maxSelections}</span>
            </div>
            <div className="seed-card__rows">
              <div>
                <p className="seed-card__label">I like...</p>
                <div className="seed-chip-row">
                  {section.options.map((option) => (
                    <button
                      key={`like-${section.field}-${option}`}
                      type="button"
                      className={`seed-chip ${(likes[section.field] || []).includes(option) ? 'selected' : ''}`}
                      onClick={() => toggleToken(section.field, option, likes, setLikes, dislikes, setDislikes, maxSelections)}
                      disabled={loading}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="seed-card__label">Less of this...</p>
                <div className="seed-chip-row">
                  {section.options.map((option) => (
                    <button
                      key={`dislike-${section.field}-${option}`}
                      type="button"
                      className={`seed-chip seed-chip--muted ${(dislikes[section.field] || []).includes(option) ? 'selected' : ''}`}
                      onClick={() => toggleToken(section.field, option, dislikes, setDislikes, likes, setLikes, maxSelections)}
                      disabled={loading}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

export default function BetaSeedScreen({ category, onSkip, onSubmit, loading }) {
  const [likes, setLikes] = useState({});
  const [dislikes, setDislikes] = useState({});
  const [likedTitles, setLikedTitles] = useState([]);
  const [dislikedTitles, setDislikedTitles] = useState([]);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState('');
  const maxSelections = 5;

  const config = useMemo(() => {
    if (category === 'movies') {
      return {
        title: 'Tell the model what kinds of movies pull you in first.',
        description: 'These signals help the AI choose a better 100-item opening pool before you pick your 10 favorites.',
        sections: [
          { field: 'genres', label: 'Genres', options: ['Drama', 'Comedy', 'Action', 'Sci-Fi', 'Thriller', 'Romance', 'Horror', 'Adventure'] },
          { field: 'directors', label: 'Directors', options: ['Christopher Nolan', 'Greta Gerwig', 'Denis Villeneuve', 'Jordan Peele', 'Hayao Miyazaki', 'David Fincher'] },
        ],
      };
    }
    if (category === 'games') {
      return {
        title: 'Prime the AI with the game styles you reach for first.',
        description: 'Use genres, play patterns, and a few favorite titles so the first sample already feels closer to your taste.',
        sections: [
          { field: 'genres', label: 'Genres', options: ['RPG', 'Action', 'Strategy', 'Adventure', 'Shooter', 'Simulation', 'Sports', 'Puzzle'] },
          { field: 'platforms', label: 'Platforms', options: ['PC', 'PlayStation 5', 'Nintendo Switch', 'Xbox Series X|S', 'PlayStation 4', 'Steam Deck'] },
        ],
      };
    }
    return {
      title: 'Give the AI a better opening signal for fountain pens.',
      description: 'Share brands, styles, and a few specific pens you like or avoid so the first 100 pens feel less random.',
      sections: [
        { field: 'vendor', label: 'Brands', options: ['Pelikan', 'Parker', 'Pilot', 'Sailor', 'Lamy', 'TWSBI', 'Visconti', 'Kaweco'] },
        { field: 'tags', label: 'Styles & traits', options: ['Demonstrator', 'Classic', 'Vintage', 'Gold Nib', 'Piston Fill', 'Travel', 'Minimalist', 'Premium'] },
      ],
    };
  }, [category]);

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
        setResults([]);
        setSearchError(err.message || 'Search failed.');
      } finally {
        setSearching(false);
      }
    }, 250);

    return () => {
      if (timerId) window.clearTimeout(timerId);
    };
  }, [query, category]);

  function addTitle(product, targetList, setTargetList, opposingList, setOpposingList) {
    if (targetList.some((item) => item.id === product.id) || targetList.length >= maxSelections) return;
    setTargetList((prev) => [...prev, product]);
    if (opposingList.some((item) => item.id === product.id)) {
      setOpposingList((prev) => prev.filter((item) => item.id !== product.id));
    }
  }

  function removeTitle(productId, setter) {
    setter((prev) => prev.filter((item) => item.id !== productId));
  }

  function handleSubmit() {
    onSubmit({
      likes,
      dislikes,
      like_product_ids: likedTitles.map((product) => product.id),
      dislike_product_ids: dislikedTitles.map((product) => product.id),
    });
  }

  return (
    <section className="screen shell seed-screen">
      <div className="seed-screen__header">
        <div>
          <p className="eyebrow">Before onboarding</p>
          <h2>{config.title}</h2>
          <p>{config.description}</p>
        </div>
        <button type="button" className="ghost" onClick={onSkip} disabled={loading}>
          Skip for now
        </button>
      </div>

      <SeedSection
        title="Quick preference signals"
        description="These cues shape the opening pool before you choose your 10 favorites."
        sections={config.sections}
        likes={likes}
        dislikes={dislikes}
        setLikes={setLikes}
        setDislikes={setDislikes}
        maxSelections={maxSelections}
        loading={loading}
      />

      <section className="panel seed-search-panel">
        <div className="seed-search-panel__header">
          <div>
            <p className="eyebrow">Specific titles</p>
            <h3>Search for exact items</h3>
          </div>
          <span>Optional, but helpful</span>
        </div>
        <label className="seed-search">
          <SearchRoundedIcon fontSize="small" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search titles, brands, studios, or games"
            disabled={loading}
          />
        </label>
        {searching && <p className="muted">Searching...</p>}
        {searchError && <p className="muted">{searchError}</p>}

        <div className="seed-picked-grid">
          <div className="seed-picked-card">
            <strong>Like these</strong>
            <div className="seed-picked-list">
              {likedTitles.length === 0 && <span className="seed-empty">Nothing added yet.</span>}
              {likedTitles.map((item) => (
                <button key={item.id} type="button" className="seed-chip selected" onClick={() => removeTitle(item.id, setLikedTitles)}>
                  {item.title}
                </button>
              ))}
            </div>
          </div>
          <div className="seed-picked-card">
            <strong>Less of these</strong>
            <div className="seed-picked-list">
              {dislikedTitles.length === 0 && <span className="seed-empty">Nothing added yet.</span>}
              {dislikedTitles.map((item) => (
                <button key={item.id} type="button" className="seed-chip seed-chip--muted selected" onClick={() => removeTitle(item.id, setDislikedTitles)}>
                  {item.title}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="seed-results">
          {results.map((item) => (
            <article key={item.id} className="seed-result">
              <div className="seed-result__main">
                <strong>{item.title}</strong>
                <span>
                  {item.vendor || item.data?.directors?.[0] || item.data?.platforms?.[0] || item.category}
                </span>
              </div>
              <div className="seed-result__actions">
                <button
                  type="button"
                  className="secondary-btn"
                  onClick={() => addTitle(item, likedTitles, setLikedTitles, dislikedTitles, setDislikedTitles)}
                  disabled={loading || likedTitles.length >= maxSelections}
                >
                  Like
                </button>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => addTitle(item, dislikedTitles, setDislikedTitles, likedTitles, setLikedTitles)}
                  disabled={loading || dislikedTitles.length >= maxSelections}
                >
                  Less of
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      <div className="round-actions round-actions--split">
        <p className="muted">You can skip this and still play. Adding a few signals just gives the AI a smarter head start.</p>
        <div className="round-actions__cluster">
          <button type="button" className="ghost" onClick={onSkip} disabled={loading}>
            Skip
          </button>
          <button type="button" onClick={handleSubmit} disabled={loading}>
            {loading ? 'Saving...' : 'Build my opening pool'}
          </button>
        </div>
      </div>
    </section>
  );
}
