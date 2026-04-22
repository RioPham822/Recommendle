import { useEffect, useMemo, useState } from 'react';
import {
  clearAdminUserProgress,
  createPersonaRun,
  deleteAdminUser,
  exportAdminProducts,
  getAdminMe,
  getAdminMlConfig,
  getPersonaRunDetail,
  getAdminUserMlStats,
  listAdminPersonas,
  listAdminCategories,
  listAdminProducts,
  listAdminUsers,
  listPersonaRuns,
  updateAdminMlConfig,
} from '../lib/api';

const PAGE_SIZE = 100;
const TERMINAL_PERSONA_RUN_STATUSES = new Set(['completed', 'failed', 'max_rounds_reached', 'superseded']);

function formatCellValue(value) {
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '-';
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return Number.isInteger(numeric) ? numeric.toLocaleString() : numeric.toFixed(1);
}

function formatDate(value) {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleDateString();
}

function ChipList({ items = [], tone = 'neutral' }) {
  if (!items || items.length === 0) return <span className="admin-empty">-</span>;
  return (
    <div className="admin-chip-list">
      {items.slice(0, 8).map((item, index) => {
        const label = Array.isArray(item) ? item[0] : item;
        const weight = Array.isArray(item) ? item[1] : null;
        return (
          <span key={`${label}-${index}`} className={`admin-chip admin-chip--${tone}`}>
            {label}
            {weight !== null && weight !== undefined ? <strong>{weight}</strong> : null}
          </span>
        );
      })}
    </div>
  );
}

function ProductCell({ column, value, row }) {
  switch (column.kind) {
    case 'thumbnail':
      return row.image_url ? (
        <img
          className="admin-table-thumb"
          src={row.image_url}
          alt={row.title ? `${row.title} cover` : 'Product thumbnail'}
          loading="lazy"
        />
      ) : (
        <div className="admin-table-thumb admin-table-thumb--placeholder" aria-hidden="true">
          {String(formatCellValue(row.title)).slice(0, 1).toUpperCase()}
        </div>
      );
    case 'title':
      return (
        <div className="admin-title-cell">
          <strong>{formatCellValue(value)}</strong>
          <span>{row.id}</span>
        </div>
      );
    case 'chips':
      return <ChipList items={Array.isArray(value) ? value : []} />;
    case 'badge':
      return value ? <span className="admin-badge">{String(value)}</span> : <span className="admin-empty">-</span>;
    case 'rating':
      return value ? <span className="admin-score">{formatNumber(value)}</span> : <span className="admin-empty">-</span>;
    case 'number':
      return <span>{formatNumber(value)}</span>;
    case 'date':
      return <span>{formatDate(value)}</span>;
    case 'link':
      return value ? <a href={value} target="_blank" rel="noreferrer" className="admin-link-button">Open</a> : <span className="admin-empty">-</span>;
    case 'long_text':
      return value ? <p className="admin-description-cell">{String(value)}</p> : <span className="admin-empty">-</span>;
    default:
      return <span>{formatCellValue(value)}</span>;
  }
}

function ProductCard({ row, columns, selected, onSelect }) {
  const metaColumns = columns.filter((column) => ['badge', 'rating', 'number', 'date'].includes(column.kind));
  const summaryColumns = columns.filter((column) => ['chips', 'long_text'].includes(column.kind));
  const primaryMeta = metaColumns
    .filter((column) => row[column.key] !== null && row[column.key] !== undefined && row[column.key] !== '')
    .slice(0, 4);
  const summaryColumn = summaryColumns.find((column) => row[column.key]);

  return (
    <button
      type="button"
      className={`admin-product-card ${selected ? 'active' : ''}`}
      onClick={() => onSelect(row)}
    >
      <div className="admin-product-card__media">
        {row.image_url ? (
          <img src={row.image_url} alt={row.title ? `${row.title} cover` : 'Product thumbnail'} loading="lazy" />
        ) : (
          <div className="admin-product-card__placeholder" aria-hidden="true">
            {String(formatCellValue(row.title)).slice(0, 1).toUpperCase()}
          </div>
        )}
      </div>
      <div className="admin-product-card__body">
        <h3>{formatCellValue(row.title)}</h3>
        {row.vendor ? <p className="admin-product-card__vendor">{row.vendor}</p> : null}
        {primaryMeta.length ? (
          <div className="admin-product-card__meta">
            {primaryMeta.map((column) => (
              <span key={`${row.id}-${column.key}`} className="admin-product-card__meta-pill">
                {column.kind === 'rating' || column.kind === 'number' ? formatNumber(row[column.key]) : formatCellValue(row[column.key])}
              </span>
            ))}
          </div>
        ) : null}
        {summaryColumn ? (
          <div className="admin-product-card__summary">
            <ProductCell column={summaryColumn} value={row[summaryColumn.key]} row={row} />
          </div>
        ) : null}
      </div>
    </button>
  );
}

function ProductDetailPanel({ row, columns }) {
  if (!row) {
    return (
      <div className="admin-product-detail admin-product-detail--empty">
        <h3>Select a product</h3>
        <p>Pick a card to inspect the full product record.</p>
      </div>
    );
  }

  const detailColumns = columns.filter((column) => column.key !== 'thumbnail');

  return (
    <div className="admin-product-detail">
      <div className="admin-product-detail__hero">
        <div className="admin-product-detail__image">
          {row.image_url ? (
            <img src={row.image_url} alt={row.title ? `${row.title} cover` : 'Product thumbnail'} loading="lazy" />
          ) : (
            <div className="admin-product-detail__placeholder" aria-hidden="true">
              {String(formatCellValue(row.title)).slice(0, 1).toUpperCase()}
            </div>
          )}
        </div>
        <div className="admin-product-detail__intro">
          <p className="eyebrow">Product details</p>
          <h3>{formatCellValue(row.title)}</h3>
          <p>{row.vendor || row.id}</p>
        </div>
      </div>
      <div className="admin-product-detail__grid">
        {detailColumns.map((column) => (
          <section key={`${row.id}-${column.key}`} className="admin-product-detail__field">
            <h4>{column.label}</h4>
            <div>
              <ProductCell column={column} value={row[column.key]} row={row} />
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function MlProfileCard({ profile }) {
  return (
    <article className="admin-ml-card">
      <div className="admin-ml-card__header">
        <div>
          <h4>{profile.display_name}</h4>
          <p>{profile.status || 'No active run'} / {profile.rounds_played || 0} rounds</p>
        </div>
        <div className="admin-ml-card__metrics">
          <span>Vector {profile.vector_strength}</span>
          <span>Selections {profile.selection_count}</span>
          <span>Negative {profile.negative_feedback_count}</span>
        </div>
      </div>
      <div className="admin-ml-grid">
        <section>
          <h5>Likes / affinities</h5>
          <ChipList items={profile.learned_preferences} tone="positive" />
        </section>
        <section>
          <h5>Dislikes</h5>
          <ChipList items={profile.learned_dislikes} tone="negative" />
        </section>
        <section>
          <h5>Hidden affinities</h5>
          <ChipList items={profile.hidden_preferences} tone="info" />
        </section>
        <section>
          <h5>Explicit negative signals</h5>
          <ChipList items={profile.disliked_signals} tone="negative" />
        </section>
      </div>
      <section className="admin-ml-card__deck">
        <h5>Current preference deck</h5>
        {profile.preference_deck?.length ? (
          <div className="admin-deck-grid">
            {profile.preference_deck.map((item) => (
              <div key={item.id} className="admin-deck-item">
                <strong>{item.title}</strong>
                <span>{item.subtitle || item.vendor || profile.display_name}</span>
              </div>
            ))}
          </div>
        ) : (
          <p className="admin-empty">No preference deck stored yet.</p>
        )}
      </section>
    </article>
  );
}

function ResumableRunList({ runs = [] }) {
  if (!runs.length) return null;
  return (
    <section className="admin-user-runs">
      <h4>Active / resumable runs</h4>
      <div className="admin-user-runs__grid">
        {runs.map((run) => (
          <article key={`${run.category}-${run.game_id}`} className="admin-user-runs__card">
            <strong>{run.display_name}</strong>
            <span>Status: {run.status || 'Unknown'}</span>
            <span>
              Continue from round {Math.min((run.current_round || 0) + 1, run.total_rounds || (run.current_round || 0) + 1)}
            </span>
          </article>
        ))}
      </div>
    </section>
  );
}

function PersonaPreferenceGroups({ title, groups = {}, tone = 'neutral' }) {
  const entries = Object.entries(groups || {}).filter(([, values]) => Array.isArray(values) && values.length);
  if (!entries.length) return null;
  return (
    <section className="persona-pref-group">
      <h5>{title}</h5>
      <div className="persona-pref-group__rows">
        {entries.map(([field, values]) => (
          <div key={field} className="persona-pref-group__row">
            <strong>{field.replace(/_/g, ' ')}</strong>
            <ChipList items={values} tone={tone} />
          </div>
        ))}
      </div>
    </section>
  );
}

function PersonaDefinitionCard({ persona, selected, onSelect }) {
  return (
    <button
      type="button"
      className={`persona-card ${selected ? 'active' : ''}`}
      onClick={() => onSelect(persona)}
    >
      <div className="persona-card__header">
        <div>
          <p className="eyebrow">{persona.category.replace(/_/g, ' ')}</p>
          <h3>{persona.display_name}</h3>
        </div>
        <span className="admin-badge">{persona.id}</span>
      </div>
      <p className="persona-card__summary">{persona.summary}</p>
      <PersonaPreferenceGroups title="Hard likes" groups={persona.hard_likes} tone="positive" />
      <PersonaPreferenceGroups title="Soft likes" groups={persona.soft_likes} tone="info" />
      <PersonaPreferenceGroups title="Dislikes" groups={persona.dislikes} tone="negative" />
    </button>
  );
}

function PersonaRunCard({ run, selected, onSelect }) {
  return (
    <button
      type="button"
      className={`persona-run-card ${selected ? 'active' : ''}`}
      onClick={() => onSelect(run)}
    >
      <div className="persona-run-card__header">
        <div>
          <p className="eyebrow">Persona name</p>
          <strong>{run.persona_name}</strong>
          <span>{run.category.replace(/_/g, ' ')}</span>
        </div>
        <span className={`persona-run-status persona-run-status--${run.status}`}>{run.status.replace(/_/g, ' ')}</span>
      </div>
      <div className="persona-run-card__metrics">
        <span>Rounds {run.rounds_played || 0}</span>
        <span>Streak {run.current_match_streak || 0} / {run.match_streak_target || 5}</span>
        <span>Best {run.longest_match_streak || 0}</span>
      </div>
      {run.has_active_profile ? <span className="persona-run-card__profile-tag">Playable profile refreshed</span> : null}
      <p>{run.latest_message || 'Waiting for updates.'}</p>
      {run.error_message ? <p className="persona-run-card__error">{run.error_message}</p> : null}
    </button>
  );
}

function PersonaRunDetailPanel({ detail }) {
  if (!detail) {
    return (
      <div className="persona-run-detail persona-run-detail--empty">
        <h3>Select a run</h3>
        <p>Launch a persona or choose a recent run to inspect its live progress and final stats.</p>
      </div>
    );
  }

  const summary = detail.final_summary;
  const gameStatus = detail.game_status;
  const events = Array.isArray(detail.events) ? [...detail.events].reverse() : [];

  return (
    <div className="persona-run-detail">
      <div className="persona-run-detail__hero">
        <div>
          <p className="eyebrow">Run detail</p>
          <h3>{detail.persona_name}</h3>
          <p>{detail.persona?.summary}</p>
          <p><strong>Persona id:</strong> {detail.persona_id}</p>
        </div>
        <div className="persona-run-detail__hero-metrics">
          <span className={`persona-run-status persona-run-status--${detail.status}`}>{detail.status.replace(/_/g, ' ')}</span>
          <span>Target streak {detail.match_streak_target}</span>
          <span>Max rounds {detail.config?.max_rounds || '-'}</span>
          {detail.has_active_profile ? <span>Playable profile ready</span> : null}
        </div>
      </div>

      <div className="persona-run-detail__stats">
        <article>
          <h4>Live snapshot</h4>
          <p>Rounds played: <strong>{detail.rounds_played || 0}</strong></p>
          <p>Current streak: <strong>{detail.current_match_streak || 0}</strong></p>
          <p>Best streak: <strong>{detail.longest_match_streak || 0}</strong></p>
          <p>Last update: <strong>{formatDate(detail.updated_at)}</strong></p>
        </article>
        <article>
          <h4>Scores</h4>
          <p>Human score: <strong>{detail.metrics?.human_score ?? gameStatus?.human_score ?? 0}</strong></p>
          <p>AI score: <strong>{detail.metrics?.ai_score ?? gameStatus?.ai_score ?? 0}</strong></p>
          <p>Diff: <strong>{detail.metrics?.score_difference ?? 0}</strong></p>
          <p>Game id: <strong>{detail.game_id || '-'}</strong></p>
        </article>
        <article>
          <h4>Final summary</h4>
          <p>Match rate: <strong>{summary ? `${Math.round((summary.match_rate || 0) * 100)}%` : '-'}</strong></p>
          <p>Total matches: <strong>{summary?.total_matches ?? detail.total_matches ?? 0}</strong></p>
          <p>Rounds to finish: <strong>{summary?.rounds_played ?? '-'}</strong></p>
          <p>Top-3 rate: <strong>{summary ? `${Math.round((summary.accuracy?.top3_rate || 0) * 100)}%` : '-'}</strong></p>
        </article>
      </div>

      <PersonaPreferenceGroups title="Hard likes" groups={detail.persona?.hard_likes} tone="positive" />
      <PersonaPreferenceGroups title="Soft likes" groups={detail.persona?.soft_likes} tone="info" />
      <PersonaPreferenceGroups title="Dislikes" groups={detail.persona?.dislikes} tone="negative" />

      {summary?.learned_preferences?.length ? (
        <section className="persona-run-detail__chips">
          <h4>Learned preferences</h4>
          <ChipList items={summary.learned_preferences} tone="positive" />
        </section>
      ) : null}

      {summary?.hidden_preferences?.length ? (
        <section className="persona-run-detail__chips">
          <h4>Hidden preferences</h4>
          <ChipList items={summary.hidden_preferences} tone="info" />
        </section>
      ) : null}

      {summary?.top5_recommendations?.length ? (
        <section className="persona-run-detail__recommendations">
          <div className="persona-run-detail__timeline-header">
            <h4>AI Top 5 Recommendations</h4>
            <span>{summary.top5_recommendations.length} items</span>
          </div>
          <div className="persona-recommendation-grid">
            {summary.top5_recommendations.map((item) => (
              <article key={item.id} className="persona-recommendation-card">
                <div className="persona-recommendation-card__head">
                  <strong>{item.title}</strong>
                  <span className="admin-score">{formatNumber(item.score)}</span>
                </div>
                <p>{item.subtitle || item.vendor || item.category}</p>
                {item.predicted_match_features?.length ? (
                  <ChipList items={item.predicted_match_features} tone="positive" />
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {summary?.hidden_gems_products?.length ? (
        <section className="persona-run-detail__recommendations">
          <div className="persona-run-detail__timeline-header">
            <h4>Hidden Gems</h4>
            <span>{summary.hidden_gems_products.length} items</span>
          </div>
          {summary.hidden_gems_explanation ? <p className="persona-run-detail__helper">{summary.hidden_gems_explanation}</p> : null}
          <div className="persona-recommendation-grid">
            {summary.hidden_gems_products.map((item) => (
              <article key={item.id} className="persona-recommendation-card">
                <div className="persona-recommendation-card__head">
                  <strong>{item.title}</strong>
                  <span className="admin-score">{formatNumber(item.score)}</span>
                </div>
                <p>{item.subtitle || item.vendor || item.category}</p>
                {item.predicted_match_features?.length ? (
                  <ChipList items={item.predicted_match_features} tone="info" />
                ) : null}
              </article>
            ))}
          </div>
        </section>
      ) : null}

      <section className="persona-run-detail__timeline">
        <div className="persona-run-detail__timeline-header">
          <h4>Timeline</h4>
          <span>{events.length} events</span>
        </div>
        {events.length ? (
          <div className="persona-run-events">
            {events.map((event, index) => (
              <article key={`${event.timestamp}-${event.type}-${index}`} className="persona-run-event">
                <div className="persona-run-event__head">
                  <strong>{event.title}</strong>
                  <span>{formatDate(event.timestamp)}</span>
                </div>
                {event.round_number ? <p className="persona-run-event__round">Round {event.round_number}</p> : null}
                {event.detail ? <p>{event.detail}</p> : null}
                {event.data?.matched_signals?.length ? (
                  <ChipList items={event.data.matched_signals} tone="info" />
                ) : null}
                {event.data?.choices?.length ? (
                  <div className="persona-run-choice-list">
                    {event.data.choices.slice(0, 6).map((choice) => (
                      <div key={choice.product_id} className="persona-run-choice">
                        <strong>{choice.title}</strong>
                        <span>Score {formatNumber(choice.persona_score)}</span>
                      </div>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="admin-empty">No events logged yet.</p>
        )}
      </section>
    </div>
  );
}

export default function AdminScreen({ onBack }) {
  const [activeTab, setActiveTab] = useState('products');
  const [admin, setAdmin] = useState(null);
  const [categories, setCategories] = useState([]);
  const [category, setCategory] = useState('fountain_pens');
  const [search, setSearch] = useState('');
  const [filterKey, setFilterKey] = useState('');
  const [filterValue, setFilterValue] = useState('');
  const [sortField, setSortField] = useState('title');
  const [sortDir, setSortDir] = useState('asc');
  const [page, setPage] = useState(0);
  const [productTable, setProductTable] = useState({ columns: [], rows: [], total: 0, limit: PAGE_SIZE, offset: 0 });
  const [productLoading, setProductLoading] = useState(false);
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [selectedUserId, setSelectedUserId] = useState('');
  const [selectedUserStats, setSelectedUserStats] = useState(null);
  const [userStatsLoading, setUserStatsLoading] = useState(false);
  const [deletingUserId, setDeletingUserId] = useState('');
  const [clearingProgressUserId, setClearingProgressUserId] = useState('');
  const [pendingDeleteUser, setPendingDeleteUser] = useState(null);
  const [pendingProgressClearUser, setPendingProgressClearUser] = useState(null);
  const [mlConfig, setMlConfig] = useState({});
  const [mlLoading, setMlLoading] = useState(false);
  const [personas, setPersonas] = useState([]);
  const [personasLoading, setPersonasLoading] = useState(false);
  const [personaRuns, setPersonaRuns] = useState([]);
  const [personaRunsLoading, setPersonaRunsLoading] = useState(false);
  const [selectedPersonaId, setSelectedPersonaId] = useState('');
  const [selectedRunId, setSelectedRunId] = useState('');
  const [selectedRunDetail, setSelectedRunDetail] = useState(null);
  const [runDetailLoading, setRunDetailLoading] = useState(false);
  const [launchingPersona, setLaunchingPersona] = useState(false);
  const [launchMatchTarget, setLaunchMatchTarget] = useState(5);
  const [launchMaxRounds, setLaunchMaxRounds] = useState(40);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const filters = useMemo(() => (
    filterKey.trim() && filterValue.trim()
      ? { [filterKey.trim()]: filterValue.trim() }
      : {}
  ), [filterKey, filterValue]);
  const queryableColumns = useMemo(
    () => productTable.columns.filter((column) => column.key !== 'thumbnail'),
    [productTable.columns],
  );
  const selectedPersona = useMemo(
    () => personas.find((persona) => persona.id === selectedPersonaId) || null,
    [personas, selectedPersonaId],
  );
  const selectedRunIsTerminal = useMemo(
    () => TERMINAL_PERSONA_RUN_STATUSES.has(String(selectedRunDetail?.status || '').toLowerCase()),
    [selectedRunDetail],
  );

  useEffect(() => {
    async function bootstrap() {
      try {
        const [me, adminCategories] = await Promise.all([getAdminMe(), listAdminCategories()]);
        setAdmin(me);
        setCategories(adminCategories || []);
        if (Array.isArray(adminCategories) && adminCategories.length > 0) {
          setCategory(adminCategories[0].id);
        }
      } catch (loadError) {
        setError(loadError.message || 'Unable to load admin workspace.');
      }
    }
    bootstrap();
  }, []);

  useEffect(() => {
    async function loadProducts() {
      if (!category) return;
      setProductLoading(true);
      try {
        const payload = await listAdminProducts({
          category,
          search,
          filters,
          limit: PAGE_SIZE,
          offset: page * PAGE_SIZE,
          sortField,
          sortDir,
        });
        setProductTable(payload);
        setSelectedProduct((previous) => {
          if (!payload.rows?.length) return null;
          const preserved = previous ? payload.rows.find((row) => row.id === previous.id) : null;
          return preserved || payload.rows[0];
        });
        setError('');
        const nextSortableColumns = payload.columns.filter((column) => column.key !== 'thumbnail');
        if (!nextSortableColumns.find((column) => column.key === sortField) && nextSortableColumns[0]) {
          setSortField(nextSortableColumns[0].key);
        }
      } catch (loadError) {
        setError(loadError.message || 'Unable to load products.');
      } finally {
        setProductLoading(false);
      }
    }
    if (activeTab === 'products') {
      loadProducts();
    }
  }, [activeTab, category, search, filters, page, sortField, sortDir]);

  async function loadUsers() {
    setUsersLoading(true);
    try {
      const nextUsers = await listAdminUsers();
      setUsers(nextUsers);
      setError('');
      return nextUsers;
    } catch (loadError) {
      setError(loadError.message || 'Unable to load users.');
      return [];
    } finally {
      setUsersLoading(false);
    }
  }

  useEffect(() => {
    if (activeTab !== 'users') return;
    loadUsers();
  }, [activeTab]);

  async function loadPersonas() {
    setPersonasLoading(true);
    setPersonaRunsLoading(true);
    try {
      const [nextPersonas, nextRuns] = await Promise.all([
        listAdminPersonas(),
        listPersonaRuns(40),
      ]);
      setPersonas(nextPersonas || []);
      setPersonaRuns(nextRuns || []);
      setSelectedPersonaId((previous) => previous || nextPersonas?.[0]?.id || '');
      setSelectedRunId((previous) => previous || nextRuns?.[0]?.id || '');
      setError('');
      return { nextPersonas, nextRuns };
    } catch (loadError) {
      setError(loadError.message || 'Unable to load persona simulations.');
      return { nextPersonas: [], nextRuns: [] };
    } finally {
      setPersonasLoading(false);
      setPersonaRunsLoading(false);
    }
  }

  async function refreshPersonaRuns() {
    setPersonaRunsLoading(true);
    try {
      const nextRuns = await listPersonaRuns(40);
      setPersonaRuns(nextRuns || []);
      setSelectedRunId((previous) => previous || nextRuns?.[0]?.id || '');
      setError('');
      return nextRuns || [];
    } catch (loadError) {
      setError(loadError.message || 'Unable to refresh persona runs.');
      return [];
    } finally {
      setPersonaRunsLoading(false);
    }
  }

  useEffect(() => {
    if (!['personas', 'persona-stats'].includes(activeTab)) return;
    loadPersonas();
  }, [activeTab]);

  useEffect(() => {
    if (!selectedUserId || activeTab !== 'users' || deletingUserId === selectedUserId || clearingProgressUserId === selectedUserId) return;
    async function loadUserStats() {
      setUserStatsLoading(true);
      try {
        setSelectedUserStats(await getAdminUserMlStats(selectedUserId));
        setError('');
      } catch (loadError) {
        if (String(loadError.message || '').toLowerCase().includes('user not found')) {
          setSelectedUserStats(null);
          return;
        }
        setError(loadError.message || 'Unable to load ML profile.');
      } finally {
        setUserStatsLoading(false);
      }
    }
    loadUserStats();
  }, [selectedUserId, activeTab, deletingUserId, clearingProgressUserId]);

  useEffect(() => {
    if (!selectedRunId || !['personas', 'persona-stats'].includes(activeTab)) return;
    let cancelled = false;
    async function loadRunDetail() {
      setRunDetailLoading(true);
      try {
        const payload = await getPersonaRunDetail(selectedRunId);
        if (!cancelled) {
          setSelectedRunDetail(payload);
          setError('');
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError.message || 'Unable to load persona run detail.');
        }
      } finally {
        if (!cancelled) {
          setRunDetailLoading(false);
        }
      }
    }
    loadRunDetail();
    return () => {
      cancelled = true;
    };
  }, [selectedRunId, activeTab]);

  useEffect(() => {
    if (!['personas', 'persona-stats'].includes(activeTab) || selectedRunIsTerminal) return undefined;
    const intervalId = window.setInterval(async () => {
      const nextRuns = await refreshPersonaRuns();
      if (selectedRunId) {
        const selected = nextRuns.find((run) => run.id === selectedRunId);
        if (!selected) {
          setSelectedRunId(nextRuns?.[0]?.id || '');
        } else {
          try {
            setSelectedRunDetail(await getPersonaRunDetail(selectedRunId));
          } catch {
            // Keep the previous detail payload if polling detail fails once.
          }
        }
      } else if (nextRuns.length) {
        setSelectedRunId(nextRuns[0].id);
      }
    }, 3000);
    return () => window.clearInterval(intervalId);
  }, [activeTab, selectedRunId, selectedRunIsTerminal]);

  useEffect(() => {
    if (!message) return undefined;
    const timeoutId = window.setTimeout(() => setMessage(''), 4000);
    return () => window.clearTimeout(timeoutId);
  }, [message]);

  useEffect(() => {
    if (!error) return undefined;
    const timeoutId = window.setTimeout(() => setError(''), 5000);
    return () => window.clearTimeout(timeoutId);
  }, [error]);

  useEffect(() => {
    if (activeTab !== 'ml') return;
    async function loadMlConfig() {
      setMlLoading(true);
      try {
        setMlConfig(await getAdminMlConfig());
        setError('');
      } catch (loadError) {
        setError(loadError.message || 'Unable to load ML settings.');
      } finally {
        setMlLoading(false);
      }
    }
    loadMlConfig();
  }, [activeTab]);

  async function handleExportProducts() {
    setError('');
    setMessage('');
    try {
      await exportAdminProducts({ category, search, filters });
      setMessage('CSV export downloaded. You can open it directly in Excel.');
    } catch (downloadError) {
      setError(downloadError.message || 'Unable to export products.');
    }
  }

  async function confirmDeleteUser() {
    if (!pendingDeleteUser) return;
    const userId = pendingDeleteUser.id;
    setError('');
    setMessage('');
    setDeletingUserId(userId);
    setSelectedUserStats(null);
    setPendingDeleteUser(null);
    try {
      const result = await deleteAdminUser(userId);
      const nextUsers = await loadUsers();
      const deletedIndex = users.findIndex((user) => user.id === userId);
      const nextUser =
        nextUsers[deletedIndex] ||
        nextUsers[Math.max(0, deletedIndex - 1)] ||
        null;
      setSelectedUserId(nextUser?.id || '');
      setMessage(`User deleted. Removed ${result.deleted_game_count || 0} related game records.`);
    } catch (deleteError) {
      setError(deleteError.message || 'Unable to delete user.');
      if (selectedUserId === userId) {
        try {
          setSelectedUserStats(await getAdminUserMlStats(userId));
        } catch {
          setSelectedUserStats(null);
        }
      }
    } finally {
      setDeletingUserId('');
    }
  }

  async function confirmClearUserProgress() {
    if (!pendingProgressClearUser) return;
    const userId = pendingProgressClearUser.id;
    setError('');
    setMessage('');
    setClearingProgressUserId(userId);
    setPendingProgressClearUser(null);
    try {
      const result = await clearAdminUserProgress(userId);
      const nextUsers = await loadUsers();
      const refreshedUser = nextUsers.find((user) => user.id === userId) || null;
      if (selectedUserId === userId) {
        if (refreshedUser) {
          setSelectedUserStats(await getAdminUserMlStats(userId));
        } else {
          setSelectedUserStats(null);
        }
      }
      setMessage(`Cleared ${result.cleared_game_count || 0} game record${result.cleared_game_count === 1 ? '' : 's'} for ${pendingProgressClearUser.display_name}.`);
    } catch (progressError) {
      setError(progressError.message || 'Unable to clear user progress.');
    } finally {
      setClearingProgressUserId('');
    }
  }

  async function handleLaunchPersonaRun() {
    if (!selectedPersonaId) return;
    setLaunchingPersona(true);
    setError('');
    setMessage('');
    try {
      const detail = await createPersonaRun({
        personaId: selectedPersonaId,
        matchStreakTarget: Number(launchMatchTarget) || 5,
        maxRounds: Number(launchMaxRounds) || 40,
      });
      setSelectedRunId(detail.id);
      setSelectedRunDetail(detail);
      await refreshPersonaRuns();
      setMessage(`Started simulation for ${detail.persona_name}.`);
    } catch (launchError) {
      setError(launchError.message || 'Unable to start persona simulation.');
    } finally {
      setLaunchingPersona(false);
    }
  }

  async function handleSaveMlConfig() {
    setMlLoading(true);
    setError('');
    setMessage('');
    try {
      const updated = await updateAdminMlConfig(mlConfig);
      setMlConfig(updated.values || {});
      setMessage('ML parameters updated. New rounds will use the new values.');
    } catch (updateError) {
      setError(updateError.message || 'Unable to save ML config.');
    } finally {
      setMlLoading(false);
    }
  }

  const totalPages = Math.max(1, Math.ceil((productTable.total || 0) / PAGE_SIZE));

  return (
    <section className="screen shell admin-screen">
      <div className="admin-screen__header">
        <div>
          <p className="eyebrow">Admin workspace</p>
          <h1>Control users, catalogs, and model tuning</h1>
          <p className="admin-screen__meta">
            Signed in as {admin?.display_name || 'Admin'} ({admin?.username || '...'})
          </p>
        </div>
        <button type="button" className="ghost" onClick={onBack}>Back to game</button>
      </div>

      {(message || error) && (
        <div className={`admin-screen__banner ${error ? 'error' : 'success'}`}>
          {error || message}
        </div>
      )}

      <div className="admin-tabs">
        <button type="button" className={activeTab === 'products' ? 'active' : ''} onClick={() => setActiveTab('products')}>Products</button>
        <button type="button" className={activeTab === 'users' ? 'active' : ''} onClick={() => setActiveTab('users')}>Users</button>
        <button type="button" className={activeTab === 'personas' ? 'active' : ''} onClick={() => setActiveTab('personas')}>Persona Library</button>
        <button type="button" className={activeTab === 'persona-stats' ? 'active' : ''} onClick={() => setActiveTab('persona-stats')}>Persona Stats</button>
        <button type="button" className={activeTab === 'ml' ? 'active' : ''} onClick={() => setActiveTab('ml')}>ML Settings</button>
      </div>

      {activeTab === 'products' && (
        <div className="admin-panel">
          <div className="admin-products-layout">
            <aside className="admin-products-sidebar">
              <div className="admin-toolbar admin-toolbar--stacked">
                <label>
                  <span>Category</span>
                  <select
                    value={category}
                    onChange={(event) => {
                      setCategory(event.target.value);
                      setPage(0);
                      setFilterKey('');
                      setFilterValue('');
                      setSortField('title');
                    }}
                  >
                    {categories.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                  </select>
                </label>
                <label>
                  <span>Search</span>
                  <input value={search} onChange={(event) => { setSearch(event.target.value); setPage(0); }} placeholder="Title or vendor" />
                </label>
                <label>
                  <span>Filter column</span>
                  <select value={filterKey} onChange={(event) => { setFilterKey(event.target.value); setPage(0); }}>
                    <option value="">None</option>
                    {queryableColumns.map((column) => (
                      <option key={column.key} value={column.key}>{column.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Filter value</span>
                  <input value={filterValue} onChange={(event) => { setFilterValue(event.target.value); setPage(0); }} placeholder="Contains..." />
                </label>
                <label>
                  <span>Sort by</span>
                  <select value={sortField} onChange={(event) => setSortField(event.target.value)}>
                    {queryableColumns.map((column) => (
                      <option key={column.key} value={column.key}>{column.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Direction</span>
                  <select value={sortDir} onChange={(event) => setSortDir(event.target.value)}>
                    <option value="asc">Ascending</option>
                    <option value="desc">Descending</option>
                  </select>
                </label>
                <button type="button" className="ghost" onClick={handleExportProducts}>Export CSV</button>
              </div>
            </aside>

            <div className="admin-products-main">
              <div className="admin-products-header">
                <div>
                  <p className="eyebrow">Catalog view</p>
                  <h2>{categories.find((item) => item.id === category)?.display_name || 'Products'}</h2>
                </div>
                <span className="admin-products-count">{productTable.total || 0} products</span>
              </div>

              <div className="admin-products-content">
                <div className="admin-products-grid">
                  {productLoading ? (
                    <div className="admin-products-empty">Loading products...</div>
                  ) : productTable.rows.length === 0 ? (
                    <div className="admin-products-empty">No products found.</div>
                  ) : productTable.rows.map((row) => (
                    <ProductCard
                      key={row.id}
                      row={row}
                      columns={queryableColumns}
                      selected={selectedProduct?.id === row.id}
                      onSelect={setSelectedProduct}
                    />
                  ))}
                </div>

                <ProductDetailPanel row={selectedProduct} columns={productTable.columns} />
              </div>
            </div>
          </div>

          <div className="admin-pagination">
            <span>{productTable.total || 0} total products</span>
            <button type="button" className="ghost" disabled={page <= 0} onClick={() => setPage((previous) => Math.max(previous - 1, 0))}>Previous</button>
            <span>Page {page + 1} of {totalPages}</span>
            <button type="button" className="ghost" disabled={page + 1 >= totalPages} onClick={() => setPage((previous) => previous + 1)}>Next</button>
          </div>
        </div>
      )}

      {activeTab === 'users' && (
        <div className={`admin-users-layout ${deletingUserId || clearingProgressUserId ? 'admin-users-layout--busy' : ''}`}>
          <div className="admin-panel">
            <div className="admin-user-list">
              {usersLoading ? (
                <p>Loading users...</p>
              ) : users.map((user) => (
                <button
                  type="button"
                  key={user.id}
                  className={`admin-user-card ${selectedUserId === user.id ? 'active' : ''}`}
                  onClick={() => setSelectedUserId(user.id)}
                  disabled={Boolean(deletingUserId || clearingProgressUserId)}
                >
                  <strong>{user.display_name}</strong>
                  <span>@{user.username}</span>
                  <span>
                    {deletingUserId === user.id
                      ? 'Deleting user...'
                      : clearingProgressUserId === user.id
                        ? 'Clearing game progress...'
                        : 'View user details'}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div className="admin-panel admin-user-detail">
            {deletingUserId && deletingUserId === selectedUserId ? (
              <div className="admin-user-state">
                <h3>Deleting user account...</h3>
                <p>The backend is removing the user, games, preferences, and stored ML data. This can take a moment.</p>
              </div>
            ) : clearingProgressUserId && clearingProgressUserId === selectedUserId ? (
              <div className="admin-user-state">
                <h3>Clearing game progress...</h3>
                <p>The backend is removing this user's previous and ongoing game history while keeping the account.</p>
              </div>
            ) : !selectedUserId ? (
              <p>Select a user to inspect their model profile.</p>
            ) : userStatsLoading ? (
              <p>Loading ML profile...</p>
            ) : selectedUserStats ? (
              <>
                <div className="admin-user-detail__header">
                  <div>
                    <h3>{selectedUserStats.user.display_name}</h3>
                    <p>@{selectedUserStats.user.username}</p>
                    <p>{(selectedUserStats.user.resumable_runs || []).length} active or resumable runs</p>
                  </div>
                  <div className="admin-user-detail__actions">
                    <button
                      type="button"
                      className="ghost"
                      onClick={() => setPendingProgressClearUser(selectedUserStats.user)}
                      disabled={Boolean(deletingUserId || clearingProgressUserId)}
                    >
                      Clear game progress
                    </button>
                    <button
                      type="button"
                      className="ghost danger"
                      onClick={() => setPendingDeleteUser(selectedUserStats.user)}
                      disabled={Boolean(deletingUserId || clearingProgressUserId)}
                    >
                      {deletingUserId === selectedUserId ? 'Deleting...' : 'Delete user account'}
                    </button>
                  </div>
                </div>
                <ResumableRunList runs={selectedUserStats.user.resumable_runs || []} />
                {selectedUserStats.profiles.length ? (
                  <div className="admin-ml-profile-list">
                    {selectedUserStats.profiles.map((profile) => (
                      <MlProfileCard key={profile.category} profile={profile} />
                    ))}
                  </div>
                ) : (
                  <p>No ML stats are stored for this user yet.</p>
                )}
              </>
            ) : (
              <p>Unable to load that user.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'personas' && (
        <div className="persona-admin-layout persona-admin-layout--library">
          <aside className="admin-panel persona-admin-sidebar">
            <div className="persona-launch-panel">
              <div>
                <p className="eyebrow">Persona simulator</p>
                <h2>Launch a live run</h2>
                <p>Start a bundled persona in beta mode and watch the run update inside admin.</p>
              </div>

              <label>
                <span>Match streak target</span>
                <input
                  type="number"
                  min="1"
                  max="50"
                  value={launchMatchTarget}
                  onChange={(event) => setLaunchMatchTarget(event.target.value)}
                />
              </label>

              <label>
                <span>Max rounds safety cap</span>
                <input
                  type="number"
                  min="1"
                  max="200"
                  value={launchMaxRounds}
                  onChange={(event) => setLaunchMaxRounds(event.target.value)}
                />
              </label>

              <button type="button" onClick={handleLaunchPersonaRun} disabled={!selectedPersonaId || launchingPersona}>
                {launchingPersona ? 'Launching...' : selectedPersona ? `Launch ${selectedPersona.display_name}` : 'Select a persona'}
              </button>
            </div>
          </aside>

          <div className="admin-panel persona-library">
            <div className="persona-library__header">
              <div>
                <p className="eyebrow">Persona library</p>
                <h2>Choose a named persona</h2>
              </div>
              <span>{personas.length} personas</span>
            </div>
            {personasLoading ? (
              <p>Loading personas...</p>
            ) : personas.length ? (
              <div className="persona-library__list">
                {personas.map((persona) => (
                  <PersonaDefinitionCard
                    key={persona.id}
                    persona={persona}
                    selected={selectedPersonaId === persona.id}
                    onSelect={(nextPersona) => setSelectedPersonaId(nextPersona.id)}
                  />
                ))}
              </div>
            ) : (
              <p className="admin-empty">No personas available.</p>
            )}
          </div>
        </div>
      )}

      {activeTab === 'persona-stats' && (
        <div className="persona-admin-layout">
          <div className="persona-admin-main">
            <div className="admin-panel persona-run-board">
              <div className="persona-run-board__header">
                <div>
                  <p className="eyebrow">Persona stats</p>
                  <h2>Live runs and final results</h2>
                </div>
                <button type="button" className="ghost" onClick={refreshPersonaRuns} disabled={personaRunsLoading}>
                  {personaRunsLoading ? 'Refreshing...' : 'Refresh'}
                </button>
              </div>

              {personaRuns.length ? (
                <div className="persona-run-board__list">
                  {personaRuns.map((run) => (
                    <PersonaRunCard
                      key={run.id}
                      run={run}
                      selected={selectedRunId === run.id}
                      onSelect={(nextRun) => setSelectedRunId(nextRun.id)}
                    />
                  ))}
                </div>
              ) : (
                <div className="admin-products-empty">No persona runs yet. Launch one from the Persona Library tab.</div>
              )}
            </div>
          </div>

          <div className="admin-panel">
            {runDetailLoading && !selectedRunDetail ? (
              <p>Loading run detail...</p>
            ) : (
              <PersonaRunDetailPanel detail={selectedRunDetail} />
            )}
          </div>
        </div>
      )}

      {pendingDeleteUser ? (
        <div className="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-delete-title">
          <div className="admin-modal__card admin-modal__card--compact">
            <h3 id="admin-delete-title">Delete user account?</h3>
            <p className="admin-modal__copy">
              This will permanently remove <strong>{pendingDeleteUser.display_name}</strong>, including their games, preferences, and stored ML data.
            </p>
            <p className="admin-modal__copy admin-modal__warning">This action cannot be undone.</p>
            <div className="admin-modal__actions">
              <button type="button" className="ghost" onClick={() => setPendingDeleteUser(null)}>
                Cancel
              </button>
              <button type="button" className="danger-fill" onClick={confirmDeleteUser}>
                Delete user
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {pendingProgressClearUser ? (
        <div className="admin-modal" role="dialog" aria-modal="true" aria-labelledby="admin-progress-title">
          <div className="admin-modal__card admin-modal__card--compact">
            <h3 id="admin-progress-title">Clear all game progress?</h3>
            <p className="admin-modal__copy">
              This will remove all previous and ongoing runs for <strong>{pendingProgressClearUser.display_name}</strong>.
            </p>
            <p className="admin-modal__copy">Their account will remain, but their run history, resumable runs, and stored in-game ML progress will be cleared.</p>
            <div className="admin-modal__actions">
              <button type="button" className="ghost" onClick={() => setPendingProgressClearUser(null)}>
                Cancel
              </button>
              <button type="button" onClick={confirmClearUserProgress}>
                Clear progress
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {activeTab === 'ml' && (
        <div className="admin-panel admin-panel--form">
          {Object.keys(mlConfig).length === 0 && mlLoading ? (
            <p>Loading ML settings...</p>
          ) : (
            <>
              {Object.keys(mlConfig).map((key) => (
                <label key={key} className="admin-ml-field">
                  <span>{key}</span>
                  <input
                    type="number"
                    step="0.01"
                    value={mlConfig[key]}
                    onChange={(event) => {
                      const nextValue = event.target.value;
                      setMlConfig((previous) => ({ ...previous, [key]: nextValue }));
                    }}
                  />
                </label>
              ))}
              <button type="button" onClick={handleSaveMlConfig} disabled={mlLoading}>Save ML parameters</button>
            </>
          )}
        </div>
      )}
    </section>
  );
}
