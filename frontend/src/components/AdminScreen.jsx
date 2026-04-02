import { useEffect, useMemo, useState } from 'react';
import {
  clearAdminUserProgress,
  deleteAdminUser,
  exportAdminProducts,
  getAdminMe,
  getAdminMlConfig,
  getAdminUserMlStats,
  listAdminCategories,
  listAdminProducts,
  listAdminUsers,
  updateAdminMlConfig,
} from '../lib/api';

const PAGE_SIZE = 100;

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
