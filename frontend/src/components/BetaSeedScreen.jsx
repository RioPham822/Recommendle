import { useEffect, useMemo, useState } from 'react';
import CloseRoundedIcon from '@mui/icons-material/CloseRounded';
import SearchRoundedIcon from '@mui/icons-material/SearchRounded';
import ThumbDownAltOutlinedIcon from '@mui/icons-material/ThumbDownAltOutlined';
import ThumbUpAltOutlinedIcon from '@mui/icons-material/ThumbUpAltOutlined';
import { searchProducts } from '../lib/api';

function getSignalState(field, value, likes, dislikes) {
  if ((likes[field] || []).includes(value)) return 'like';
  if ((dislikes[field] || []).includes(value)) return 'dislike';
  return 'neutral';
}

function toggleSignal(field, value, nextState, likes, setLikes, dislikes, setDislikes, maxSelections) {
  const currentState = getSignalState(field, value, likes, dislikes);
  if (currentState === nextState) {
    const targetSetter = nextState === 'like' ? setLikes : setDislikes;
    const currentValues = nextState === 'like' ? likes[field] || [] : dislikes[field] || [];
    targetSetter((prev) => ({ ...prev, [field]: currentValues.filter((item) => item !== value) }));
    return;
  }

  const targetState = nextState === 'like' ? likes : dislikes;
  const targetSetter = nextState === 'like' ? setLikes : setDislikes;
  const opposingState = nextState === 'like' ? dislikes : likes;
  const opposingSetter = nextState === 'like' ? setDislikes : setLikes;
  const targetValues = targetState[field] || [];
  if (targetValues.length >= maxSelections) return;

  if ((opposingState[field] || []).includes(value)) {
    opposingSetter((prev) => ({
      ...prev,
      [field]: (prev[field] || []).filter((item) => item !== value),
    }));
  }

  targetSetter((prev) => ({
    ...prev,
    [field]: [...(prev[field] || []), value],
  }));
}

function getProductImage(product) {
  if (product.image_url) return product.image_url;
  const images = product.data?.images;
  if (Array.isArray(images) && images[0]?.url) return images[0].url;
  return '';
}

function getProductMeta(product) {
  return product.vendor
    || product.data?.directors?.[0]
    || product.data?.platforms?.[0]
    || product.data?.production_companies?.[0]
    || product.category;
}

function SeedSignalTile({
  field,
  option,
  likes,
  dislikes,
  setLikes,
  setDislikes,
  maxSelections,
  loading,
}) {
  const state = getSignalState(field, option, likes, dislikes);
  const likeCount = (likes[field] || []).length;
  const dislikeCount = (dislikes[field] || []).length;
  const likeDisabled = loading || (state !== 'like' && likeCount >= maxSelections);
  const dislikeDisabled = loading || (state !== 'dislike' && dislikeCount >= maxSelections);

  return (
    <article className={`seed-signal-tile is-${state}`}>
      <div className="seed-signal-tile__header">
        <strong>{option}</strong>
        <span>
          {state === 'like' && 'Bias toward this'}
          {state === 'dislike' && 'Bias away from this'}
          {state === 'neutral' && 'Not set'}
        </span>
      </div>
      <div className="seed-signal-tile__actions">
        <button
          type="button"
          className={`seed-signal-action seed-signal-action--like ${state === 'like' ? 'active' : ''}`}
          onClick={() => toggleSignal(field, option, 'like', likes, setLikes, dislikes, setDislikes, maxSelections)}
          disabled={likeDisabled}
        >
          <ThumbUpAltOutlinedIcon fontSize="inherit" />
          <span>Like</span>
        </button>
        <button
          type="button"
          className={`seed-signal-action seed-signal-action--dislike ${state === 'dislike' ? 'active' : ''}`}
          onClick={() => toggleSignal(field, option, 'dislike', likes, setLikes, dislikes, setDislikes, maxSelections)}
          disabled={dislikeDisabled}
        >
          <ThumbDownAltOutlinedIcon fontSize="inherit" />
          <span>Dislike</span>
        </button>
      </div>
    </article>
  );
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
              <span>{`${(likes[section.field] || []).length} liked • ${(dislikes[section.field] || []).length} disliked`}</span>
            </div>
            <p className="seed-card__label">{`Pick up to ${maxSelections} to bias toward and ${maxSelections} to bias away.`}</p>
            <div className="seed-signal-grid">
              {section.options.map((option) => (
                <SeedSignalTile
                  key={`${section.field}-${option}`}
                  field={section.field}
                  option={option}
                  likes={likes}
                  dislikes={dislikes}
                  setLikes={setLikes}
                  setDislikes={setDislikes}
                  maxSelections={maxSelections}
                  loading={loading}
                />
              ))}
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
        title: 'Give the model a better movie signal.',
        description: 'Optional. Helps shape the opening 100.',
        sections: [
          { field: 'genres', label: 'Genres', options: ['Drama', 'Comedy', 'Action', 'Sci-Fi', 'Thriller', 'Romance', 'Horror', 'Adventure'] },
          { field: 'directors', label: 'Directors', options: ['Christopher Nolan', 'Greta Gerwig', 'Denis Villeneuve', 'Jordan Peele', 'Hayao Miyazaki', 'David Fincher'] },
        ],
      };
    }
    if (category === 'games') {
      return {
        title: 'Give the model a better game signal.',
        description: 'Optional. Helps shape the opening 100.',
        sections: [
          { field: 'genres', label: 'Genres', options: ['RPG', 'Action', 'Strategy', 'Adventure', 'Shooter', 'Simulation', 'Sports', 'Puzzle'] },
          { field: 'platforms', label: 'Platforms', options: ['PC', 'PlayStation 5', 'Nintendo Switch', 'Xbox Series X|S', 'PlayStation 4', 'Steam Deck'] },
        ],
      };
    }
    return {
      title: 'Give the model a better pen signal.',
      description: 'Optional. Helps shape the opening 100.',
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
        title="Quick signals"
        description="Add a few likes and dislikes."
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
            <h3>Search exact items</h3>
          </div>
          <span>Optional</span>
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
                <article key={item.id} className="seed-picked-item seed-picked-item--like">
                  <div className="seed-picked-item__media">
                    {getProductImage(item) ? (
                      <img src={getProductImage(item)} alt={item.title} loading="lazy" />
                    ) : (
                      <div className="seed-picked-item__fallback">No image</div>
                    )}
                  </div>
                  <div className="seed-picked-item__body">
                    <strong>{item.title}</strong>
                    <span>{getProductMeta(item)}</span>
                  </div>
                  <button
                    type="button"
                    className="seed-picked-item__remove"
                    onClick={() => removeTitle(item.id, setLikedTitles)}
                    aria-label={`Remove ${item.title} from liked titles`}
                  >
                    <CloseRoundedIcon fontSize="small" />
                  </button>
                </article>
              ))}
            </div>
          </div>
          <div className="seed-picked-card">
            <strong>Less of these</strong>
            <div className="seed-picked-list">
              {dislikedTitles.length === 0 && <span className="seed-empty">Nothing added yet.</span>}
              {dislikedTitles.map((item) => (
                <article key={item.id} className="seed-picked-item seed-picked-item--dislike">
                  <div className="seed-picked-item__media">
                    {getProductImage(item) ? (
                      <img src={getProductImage(item)} alt={item.title} loading="lazy" />
                    ) : (
                      <div className="seed-picked-item__fallback">No image</div>
                    )}
                  </div>
                  <div className="seed-picked-item__body">
                    <strong>{item.title}</strong>
                    <span>{getProductMeta(item)}</span>
                  </div>
                  <button
                    type="button"
                    className="seed-picked-item__remove"
                    onClick={() => removeTitle(item.id, setDislikedTitles)}
                    aria-label={`Remove ${item.title} from disliked titles`}
                  >
                    <CloseRoundedIcon fontSize="small" />
                  </button>
                </article>
              ))}
            </div>
          </div>
        </div>

        <div className="seed-results">
          {results.map((item) => (
            <article key={item.id} className="seed-result">
              <div className="seed-result__media">
                {getProductImage(item) ? (
                  <img src={getProductImage(item)} alt={item.title} loading="lazy" />
                ) : (
                  <div className="seed-result__fallback">No image</div>
                )}
              </div>
              <div className="seed-result__main">
                <strong>{item.title}</strong>
                <span>{getProductMeta(item)}</span>
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
        <p className="muted">Skip this if you want.</p>
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
