import { useEffect, useState } from 'react';
import logo from './assets/logo.svg';
import logoDark from './assets/logo-dark.svg';
import AuthScreen from './components/AuthScreen';
import AccountMenu from './components/AccountMenu';
import BrainModePanel from './components/BrainModePanel';
import FinalSummary from './components/FinalSummary';
import OnboardingGrid from './components/OnboardingGrid';
import PlayerStatsModal from './components/PlayerStatsModal';
import RoundArena from './components/RoundArena';
import RoundResultPanel from './components/RoundResultPanel';
import SetRatingModal from './components/SetRatingModal';
import WelcomeScreen from './components/WelcomeScreen';
import {
  getCategories,
  getLeaderboard,
  getOnboarding,
  getResumeState,
  startGame,
  startRound,
  submitOnboarding,
    submitRoundPick,
    logoutUser,
    getAuthToken,
    getUserId,
    getDisplayName,
    clearAuthData,
} from './lib/api';

const VIEW = {
  WELCOME: 'welcome',
  ONBOARDING: 'onboarding',
  ROUND: 'round',
  RESULT: 'result',
  FINAL: 'final',
};
const THEME_STORAGE_KEY = 'recommendle-theme';
const MIN_CATEGORY_ITEMS = 50;
const CATEGORY_RETRY_MS = 2500;
const CATEGORY_POLL_MS = 10000;

export default function App() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light';
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });
  
  // Authentication state
  const [isAuthenticated, setIsAuthenticated] = useState(() => {
    return !!localStorage.getItem('sessionToken');
  });
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState('');
  const [displayName, setDisplayName] = useState(() => {
    return localStorage.getItem('displayName') || '';
  });
  const [username, setUsername] = useState(() => {
    return localStorage.getItem('username') || '';
  });
  
  const [view, setView] = useState(VIEW.WELCOME);
  const [playerName, setPlayerName] = useState('');
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('fountain_pens');
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [categoryLoadError, setCategoryLoadError] = useState('');
  const [game, setGame] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [rating, setRating] = useState(3);
  const [ratingModalOpen, setRatingModalOpen] = useState(false);
  const [roundData, setRoundData] = useState(null);
  const [selectedRoundPick, setSelectedRoundPick] = useState('');
  const [roundResult, setRoundResult] = useState(null);
  const [leaderboard, setLeaderboard] = useState([]);
  const [mode, setMode] = useState('visual');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState({
    start: false,
    onboarding: false,
    pick: false,
    next: false,
  });
  const [welcomeLeaderboard, setWelcomeLeaderboard] = useState([]);
  const [viewingPlayer, setViewingPlayer] = useState(null);
  const [resumableGame, setResumableGame] = useState(null);
  const [resumeLoading, setResumeLoading] = useState(false);

  const activeCategory = game?.category || selectedCategory;

  // Keep player name synced to authenticated display name after reload.
  useEffect(() => {
    if (!isAuthenticated) return;
    setPlayerName((prev) => {
      if (prev.trim()) return prev;
      return displayName || getDisplayName() || '';
    });
  }, [isAuthenticated, displayName]);

  // Load category metadata and keep it fresh while datasets ingest.
  useEffect(() => {
    let cancelled = false;
    let timerId;

    const schedule = (delayMs) => {
      if (cancelled) return;
      timerId = window.setTimeout(loadCategories, delayMs);
    };

    const loadCategories = async () => {
      if (cancelled) return;
      try {
        const payload = await getCategories();
        if (cancelled) return;

        const nextCategories = Array.isArray(payload) ? payload : [];
        setCategories(nextCategories);
        setCategoriesLoading(false);
        setCategoryLoadError('');

        if (nextCategories.length > 0) {
          setSelectedCategory((prev) => {
            const hasSelected = nextCategories.some((c) => c.id === prev);
            if (hasSelected) return prev;
            const ready = nextCategories.find((c) => (c.available_count || 0) >= MIN_CATEGORY_ITEMS);
            return (ready || nextCategories[0]).id;
          });
        }

        const hasPendingDatasets = nextCategories.some(
          (category) => (category.available_count || 0) < MIN_CATEGORY_ITEMS
        );
        schedule(hasPendingDatasets ? CATEGORY_RETRY_MS : CATEGORY_POLL_MS);
      } catch (err) {
        if (cancelled) return;
        setCategoriesLoading(true);
        setCategoryLoadError(err?.message || 'Unable to load categories');
        schedule(CATEGORY_RETRY_MS);
      }
    };

    loadCategories();
    return () => {
      cancelled = true;
      if (timerId) {
        window.clearTimeout(timerId);
      }
    };
  }, []);

  // Load leaderboard for selected category on welcome screen.
  useEffect(() => {
    getLeaderboard(10, selectedCategory)
      .then(setWelcomeLeaderboard)
      .catch(() => {});
  }, [selectedCategory]);

  // Detect resumable game for current player/category on welcome screen.
  useEffect(() => {
    let cancelled = false;
    const loadResumeState = async () => {
      if (!isAuthenticated || view !== VIEW.WELCOME) {
        setResumeLoading(false);
        return;
      }
      if (categoriesLoading) {
        setResumeLoading(false);
        return;
      }
      const name = playerName.trim();
      if (!name) {
        setResumableGame(null);
        setResumeLoading(false);
        return;
      }
      setResumeLoading(true);
      try {
        const state = await getResumeState(name, selectedCategory);
        if (!cancelled) {
          setResumableGame(state);
          setResumeLoading(false);
        }
      } catch {
        if (!cancelled) {
          setResumableGame(null);
          setResumeLoading(false);
        }
      }
    };
    loadResumeState();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, view, playerName, selectedCategory, categoriesLoading]);

  // Handle login success
  const handleLoginSuccess = (authData) => {
    setIsAuthenticated(true);
    setDisplayName(authData.displayName);
    setUsername(authData.username);
    setPlayerName(authData.displayName); // Use display name as player name
    setAuthError('');
    setAuthLoading(false);
  };

  // Handle logout
  const handleLogout = async () => {
    try {
      const userId = getUserId();
      const token = getAuthToken();
      if (userId && token) {
        await logoutUser(userId, token);
      }
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      clearAuthData();
      setIsAuthenticated(false);
      setDisplayName('');
      setUsername('');
      setPlayerName('');
      resetAll();
    }
  };

  const totalRounds = game?.total_rounds ?? 5;
  const humanScore = game?.human_score ?? 0;
  const aiScore = game?.ai_score ?? 0;
  const categoryProgress = categories.length
    ? Math.round(
      (categories.reduce((sum, category) => {
        const count = Number(category.available_count) || 0;
        return sum + Math.min(count / MIN_CATEGORY_ITEMS, 1);
      }, 0) / categories.length) * 100
    )
    : 0;
  const readyCategoryCount = categories.filter(
    (category) => (Number(category.available_count) || 0) >= MIN_CATEGORY_ITEMS
  ).length;

  useEffect(() => {
    document.body.setAttribute('data-theme', theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'));
  }

  const activeLogo = theme === 'dark' ? logoDark : logo;

  function resetAll() {
    setView(VIEW.WELCOME);
    setGame(null);
    setOnboarding(null);
    setSelectedIds([]);
    setRating(3);
    setRatingModalOpen(false);
    setRoundData(null);
    setSelectedRoundPick('');
    setRoundResult(null);
    setLeaderboard([]);
    setError('');
    setResumableGame(null);
    setResumeLoading(false);
    setBusy({ start: false, onboarding: false, pick: false, next: false });
    // Refresh welcome leaderboard
    getLeaderboard(10, selectedCategory)
      .then(setWelcomeLeaderboard)
      .catch(() => {});
  }

  async function loadNextRound(gameId) {
    const round = await startRound(gameId);
    setRoundData(round);
    setSelectedRoundPick('');
    setView(VIEW.ROUND);
  }

  async function handleStart(freshStart = false) {
    setError('');
    const selected = categories.find((c) => c.id === selectedCategory);
    if (selected && selected.available_count < MIN_CATEGORY_ITEMS) {
      setError(`The ${selected.display_name} catalog is not loaded yet. Run movie ingestion first.`);
      return;
    }
    setBusy((prev) => ({ ...prev, start: true }));
    try {
      const created = await startGame(playerName, selectedCategory, freshStart);
      setGame(created);
      setSelectedIds([]);
      if (created.status === VIEW.ONBOARDING) {
        const onboardingPayload = await getOnboarding(created.id);
        setOnboarding(onboardingPayload);
        setView(VIEW.ONBOARDING);
      } else {
        setOnboarding(null);
        await loadNextRound(created.id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, start: false }));
    }
  }

  function handleToggleOnboarding(productId) {
    setSelectedIds((prev) => {
      if (prev.includes(productId)) {
        return prev.filter((id) => id !== productId);
      }
      if (prev.length >= 10) {
        return prev;
      }
      return [...prev, productId];
    });
  }

  async function handleSubmitOnboarding() {
    if (!game || selectedIds.length !== 10) {
      setError('Select exactly 10 products before continuing.');
      return;
    }

    setError('');
    setBusy((prev) => ({ ...prev, onboarding: true }));
    try {
      await submitOnboarding(game.id, selectedIds, rating);
      setGame((prev) => ({ ...prev, status: 'playing' }));
      setRatingModalOpen(false);
      await loadNextRound(game.id);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, onboarding: false }));
    }
  }

  async function handleSubmitRoundPick() {
    if (!game || !roundData || !selectedRoundPick) {
      return;
    }

    setError('');
    setBusy((prev) => ({ ...prev, pick: true }));
    try {
      const result = await submitRoundPick(game.id, roundData.round_number, selectedRoundPick);
      setRoundResult(result);
      setGame((prev) => ({
        ...prev,
        human_score: result.total_human_score,
        ai_score: result.total_ai_score,
      }));
      setView(VIEW.RESULT);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, pick: false }));
    }
  }

  async function handleResultNext() {
    if (!game || !roundResult) {
      return;
    }

    setError('');
    setBusy((prev) => ({ ...prev, next: true }));
    try {
      if (roundResult.game_complete) {
        const board = await getLeaderboard(10, activeCategory);
        setLeaderboard(board);
        setView(VIEW.FINAL);
      } else {
        await loadNextRound(game.id);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy((prev) => ({ ...prev, next: false }));
    }
  }

  async function handlePlayAgain() {
    if (!playerName.trim()) {
      return;
    }
    await handleStart(false);
  }

  return (
    <main className="app-root">
      <div className="top-right-controls">
        <button
          type="button"
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        >
          {theme === 'light' ? 'Dark Mode' : 'Light Mode'}
        </button>
        {isAuthenticated && (
          <div className="account-floating">
            <AccountMenu
              displayName={displayName}
              username={username}
              onLogout={handleLogout}
              loading={authLoading}
            />
          </div>
        )}
      </div>

      {!isAuthenticated && view === VIEW.WELCOME && (
        <header className="app-header welcome-header">
          <img src={activeLogo} alt="Recommendle" className="app-logo" />
        </header>
      )}

      {!isAuthenticated && view === VIEW.WELCOME && (
        <AuthScreen
          logoSrc={activeLogo}
          onLoginSuccess={handleLoginSuccess}
          loading={authLoading}
          error={authError}
        />
      )}

      {isAuthenticated && (
        <>
          {error && (
            <div className="error-banner">
              <span>{error}</span>
              <button type="button" onClick={() => setError('')}>Dismiss</button>
            </div>
          )}

          {view !== VIEW.WELCOME && view !== VIEW.FINAL && (
            <BrainModePanel
              mode={mode}
              onModeChange={setMode}
              categoryCopy={onboarding?.category_copy || roundData?.category_copy || roundResult?.category_copy || {}}
            />
          )}

          {view === VIEW.WELCOME && (
            <WelcomeScreen
              logoSrc={activeLogo}
              showLogo={true}
              playerName={playerName}
              setPlayerName={setPlayerName}
              categories={categories}
              selectedCategory={selectedCategory}
              setSelectedCategory={setSelectedCategory}
              onStart={() => handleStart(false)}
              onStartFresh={() => handleStart(true)}
              resumable={resumableGame}
              resumeLoading={resumeLoading}
              loading={busy.start}
              categoriesLoading={categoriesLoading}
              categoryLoadError={categoryLoadError}
              categoryProgress={categoryProgress}
              readyCategoryCount={readyCategoryCount}
              leaderboard={welcomeLeaderboard}
              onViewPlayer={(name) => setViewingPlayer(name)}
            />
          )}

          {viewingPlayer && (
            <PlayerStatsModal
              playerName={viewingPlayer}
              category={activeCategory}
              onClose={() => setViewingPlayer(null)}
            />
          )}

          {view === VIEW.ONBOARDING && onboarding && (
            <>
              <OnboardingGrid
                products={onboarding.products}
                selectedIds={selectedIds}
                onToggle={handleToggleOnboarding}
                onOpenRating={() => setRatingModalOpen(true)}
                mode={mode}
                categoryCopy={onboarding?.category_copy || {}}
              />
              <SetRatingModal
                open={ratingModalOpen}
                rating={rating}
                setRating={setRating}
                loading={busy.onboarding}
                onClose={() => setRatingModalOpen(false)}
                onSubmit={handleSubmitOnboarding}
                categoryCopy={onboarding?.category_copy || {}}
              />
            </>
          )}

          {view === VIEW.ROUND && (
            <RoundArena
              round={roundData}
              totalRounds={totalRounds}
              humanScore={humanScore}
              aiScore={aiScore}
              mode={mode}
              categoryCopy={roundData?.category_copy || {}}
              selectedPick={selectedRoundPick}
              onSelectPick={setSelectedRoundPick}
              onSubmitPick={handleSubmitRoundPick}
              submitting={busy.pick}
            />
          )}

          {view === VIEW.RESULT && (
            <RoundResultPanel
              result={roundResult}
              categoryCopy={roundResult?.category_copy || {}}
              onNext={handleResultNext}
              loadingNext={busy.next}
            />
          )}

          {view === VIEW.FINAL && (
            <FinalSummary
              playerName={playerName}
              humanScore={humanScore}
              aiScore={aiScore}
              category={activeCategory}
              gameId={game?.id}
              leaderboard={leaderboard}
              onRestart={handlePlayAgain}
              onHome={resetAll}
              onViewPlayer={(name) => setViewingPlayer(name)}
            />
          )}
        </>
      )}
    </main>
  );
}

