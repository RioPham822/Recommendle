import { useEffect, useState } from 'react';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import logo from './assets/logo.svg';
import logoDark from './assets/logo-dark.svg';
import AuthScreen from './components/AuthScreen';
import AccountMenu from './components/AccountMenu';
import AdminScreen from './components/AdminScreen';
import BetaSeedScreen from './components/BetaSeedScreen';
import BrainModePanel from './components/BrainModePanel';
import FinalSummary from './components/FinalSummary';
import OnboardingGrid from './components/OnboardingGrid';
import PlayerStatsModal from './components/PlayerStatsModal';
import RoundArena from './components/RoundArena';
import RoundResultPanel from './components/RoundResultPanel';
import SetRatingModal from './components/SetRatingModal';
import WelcomeScreen from './components/WelcomeScreen';
import {
  clearAuthData,
  getAuthToken,
  getCategories,
  getDisplayName,
  getLeaderboard,
  getOnboarding,
  getResumeState,
  getUserRole,
  getUserId,
  logoutUser,
  refreshOnboarding,
  refreshRound,
  startGame,
  startRound,
  submitOnboarding,
  submitRoundPick,
  submitSeedPreferences,
  updatePreferences,
} from './lib/api';

const VIEW = {
  WELCOME: 'welcome',
  SEED: 'seed',
  ONBOARDING: 'onboarding',
  ROUND: 'round',
  RESULT: 'result',
  FINAL: 'final',
  ADMIN: 'admin',
};

const THEME_STORAGE_KEY = 'recommendle-theme';
const MIN_CATEGORY_ITEMS = 100;
const CATEGORY_RETRY_MS = 2500;
const CATEGORY_POLL_MS = 10000;
const TRAINING_MODE = 'beta';
const MIN_ONBOARDING_SELECTIONS = 1;
const MAX_ONBOARDING_SELECTIONS = 10;

export default function App() {
  const [theme, setTheme] = useState(() => {
    if (typeof window === 'undefined') return 'light';
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  });

  const [isAuthenticated, setIsAuthenticated] = useState(() => !!localStorage.getItem('sessionToken'));
  const [displayName, setDisplayName] = useState(() => localStorage.getItem('displayName') || '');
  const [username, setUsername] = useState(() => localStorage.getItem('username') || '');
  const [userRole, setUserRole] = useState(() => getUserRole() || 'player');
  const [view, setView] = useState(VIEW.WELCOME);
  const [playerName, setPlayerName] = useState('');
  const [categories, setCategories] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState('fountain_pens');
  const [categoriesLoading, setCategoriesLoading] = useState(true);
  const [categoryLoadError, setCategoryLoadError] = useState('');
  const [game, setGame] = useState(null);
  const [onboarding, setOnboarding] = useState(null);
  const [selectedIds, setSelectedIds] = useState([]);
  const [rating, setRating] = useState(4);
  const [ratingModalOpen, setRatingModalOpen] = useState(false);
  const [roundData, setRoundData] = useState(null);
  const [selectedRoundPick, setSelectedRoundPick] = useState('');
  const [roundResult, setRoundResult] = useState(null);
  const [seenHiddenPreferenceNames, setSeenHiddenPreferenceNames] = useState([]);
  const [previousHiddenPreferenceNames, setPreviousHiddenPreferenceNames] = useState([]);
  const [lessLikeIds, setLessLikeIds] = useState([]);
  const [refreshingOnboarding, setRefreshingOnboarding] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [seedBusy, setSeedBusy] = useState(false);
  const [leaderboard, setLeaderboard] = useState([]);
  const [mode, setMode] = useState('visual');
  const [error, setError] = useState('');
  const [seedPreferences, setSeedPreferences] = useState(null);
  const [busy, setBusy] = useState({
    start: false,
    onboarding: false,
    pick: false,
    next: false,
    auth: false,
  });
  const [viewingPlayer, setViewingPlayer] = useState(null);
  const [resumableGame, setResumableGame] = useState(null);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [preferenceBusyId, setPreferenceBusyId] = useState('');

  const activeCategory = game?.category || selectedCategory;
  const activeLogo = theme === 'dark' ? logoDark : logo;
  const showHeaderBrand = !(isAuthenticated && view === VIEW.WELCOME);
  const homeHeader = !isAuthenticated || view === VIEW.WELCOME;
  const activeCategoryCount = categories.filter((category) => (Number(category.available_count) || 0) >= MIN_CATEGORY_ITEMS).length;
  const categoryProgress = categories.length
    ? Math.round(
      (categories.reduce((sum, category) => {
        const count = Number(category.available_count) || 0;
        return sum + Math.min(count / MIN_CATEGORY_ITEMS, 1);
      }, 0) / categories.length) * 100,
    )
    : 0;

  useEffect(() => {
    document.body.setAttribute('data-theme', theme);
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  }, [theme]);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'auto' });
  }, [view]);

  useEffect(() => {
    if (!isAuthenticated) return;
    setPlayerName((previous) => previous.trim() || displayName || getDisplayName() || '');
  }, [isAuthenticated, displayName]);

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
          setSelectedCategory((previous) => {
            const current = nextCategories.find((category) => category.id === previous);
            if (current) return previous;
            const firstReady = nextCategories.find((category) => (category.available_count || 0) >= MIN_CATEGORY_ITEMS);
            return (firstReady || nextCategories[0]).id;
          });
        }
        const hasPending = nextCategories.some((category) => (category.available_count || 0) < MIN_CATEGORY_ITEMS);
        schedule(hasPending ? CATEGORY_RETRY_MS : CATEGORY_POLL_MS);
      } catch (loadError) {
        if (cancelled) return;
        setCategoriesLoading(true);
        setCategoryLoadError(loadError?.message || 'Unable to load categories.');
        schedule(CATEGORY_RETRY_MS);
      }
    };

    loadCategories();
    return () => {
      cancelled = true;
      if (timerId) window.clearTimeout(timerId);
    };
  }, []);

  useEffect(() => {
    getLeaderboard(10, selectedCategory)
      .then(setLeaderboard)
      .catch(() => {});
  }, [selectedCategory]);

  useEffect(() => {
    let cancelled = false;
    async function loadResumeState() {
      if (!isAuthenticated || view !== VIEW.WELCOME || categoriesLoading || !playerName.trim()) {
        setResumeLoading(false);
        return;
      }
      setResumeLoading(true);
      try {
        const state = await getResumeState(playerName.trim(), selectedCategory);
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
    }

    loadResumeState();
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, playerName, selectedCategory, view, categoriesLoading]);

  function toggleTheme() {
    setTheme((previous) => (previous === 'light' ? 'dark' : 'light'));
  }

  function handleLoginSuccess(authData) {
    setIsAuthenticated(true);
    setDisplayName(authData.displayName);
    setUsername(authData.username);
    setUserRole(authData.role || 'player');
    setPlayerName(authData.displayName);
    setBusy((previous) => ({ ...previous, auth: false }));
  }

  async function handleLogout() {
    try {
      const userId = getUserId();
      const token = getAuthToken();
      if (userId && token) {
        await logoutUser(userId, token);
      }
    } catch (logoutError) {
      console.error('Logout failed', logoutError);
    } finally {
      clearAuthData();
      setIsAuthenticated(false);
      setDisplayName('');
      setUsername('');
      setUserRole('player');
      setPlayerName('');
      resetAll();
    }
  }

  function applyGameProgress(source) {
    setGame((previous) => {
      if (!previous) return previous;
      return {
        ...previous,
        human_score: source.total_human_score ?? source.human_score ?? previous.human_score,
        ai_score: source.total_ai_score ?? source.ai_score ?? previous.ai_score,
        current_match_streak: source.current_match_streak ?? previous.current_match_streak,
        longest_match_streak: source.longest_match_streak ?? previous.longest_match_streak,
        match_streak_target: source.match_streak_target ?? previous.match_streak_target,
        rounds_played: source.rounds_played ?? previous.rounds_played,
        status: source.game_complete ? 'completed' : source.status ?? previous.status,
      };
    });
  }

  function resetAll() {
    setView(VIEW.WELCOME);
    setGame(null);
    setOnboarding(null);
    setSelectedIds([]);
    setRating(4);
    setRatingModalOpen(false);
    setRoundData(null);
    setSelectedRoundPick('');
    setRoundResult(null);
    setSeenHiddenPreferenceNames([]);
    setPreviousHiddenPreferenceNames([]);
    setLessLikeIds([]);
    setSeedPreferences(null);
    setError('');
    setResumableGame(null);
    setResumeLoading(false);
    setPreferenceBusyId('');
    setBusy({
      start: false,
      onboarding: false,
      pick: false,
      next: false,
      auth: false,
    });
  }

  async function loadNextRound(gameId) {
    const round = await startRound(gameId);
    setRoundData(round);
    setRoundResult(null);
    setSelectedRoundPick('');
    setLessLikeIds([]);
    applyGameProgress(round);
    setView(VIEW.ROUND);
  }

  async function handleStart(freshStart = false) {
    setError('');
    const selected = categories.find((category) => category.id === selectedCategory);
    if (!selected || selected.available_count < MIN_CATEGORY_ITEMS) {
      setError(`The ${selected?.display_name || 'selected'} catalog is not ready for the 100-item onboarding pool yet.`);
      return;
    }

    setBusy((previous) => ({ ...previous, start: true }));
    try {
      const created = await startGame(playerName.trim(), selectedCategory, freshStart, TRAINING_MODE);
      setGame(created);
      setOnboarding(null);
      setSeedPreferences(null);
      setRoundData(null);
      setRoundResult(null);
      setSeenHiddenPreferenceNames([]);
      setPreviousHiddenPreferenceNames([]);
      setSelectedIds([]);
      setLessLikeIds([]);
      if (created.status === 'onboarding') {
        if (!created.resumed) {
          setView(VIEW.SEED);
        } else {
          const onboardingPayload = await getOnboarding(created.id);
          setOnboarding(onboardingPayload);
          setView(VIEW.ONBOARDING);
        }
      } else {
        await loadNextRound(created.id);
      }
    } catch (startError) {
      setError(startError.message || 'Could not start the run.');
    } finally {
      setBusy((previous) => ({ ...previous, start: false }));
    }
  }

  function handleToggleOnboarding(productId) {
    setSelectedIds((previous) => {
      if (previous.includes(productId)) {
        return previous.filter((id) => id !== productId);
      }
      if (previous.length >= MAX_ONBOARDING_SELECTIONS) {
        return previous;
      }
      return [...previous, productId];
    });
  }

  async function handleSubmitOnboarding() {
    if (!game || selectedIds.length < MIN_ONBOARDING_SELECTIONS || selectedIds.length > MAX_ONBOARDING_SELECTIONS) {
      setError(`Choose between ${MIN_ONBOARDING_SELECTIONS} and ${MAX_ONBOARDING_SELECTIONS} items before continuing.`);
      return;
    }
    setBusy((previous) => ({ ...previous, onboarding: true }));
    setError('');
    try {
      await submitOnboarding(game.id, selectedIds, rating);
      setRatingModalOpen(false);
      setGame((previous) => (previous ? { ...previous, status: 'playing' } : previous));
      await loadNextRound(game.id);
    } catch (submissionError) {
      setError(submissionError.message || 'Could not save your onboarding set.');
    } finally {
      setBusy((previous) => ({ ...previous, onboarding: false }));
    }
  }

  async function handleRefreshOnboarding() {
    if (!game) return;
    setRefreshingOnboarding(true);
    setError('');
    try {
      const refreshedOnboarding = await refreshOnboarding(game.id, selectedIds);
      setOnboarding(refreshedOnboarding);
    } catch (refreshError) {
      setError(refreshError.message || 'Could not refresh the onboarding pool.');
    } finally {
      setRefreshingOnboarding(false);
    }
  }

  async function handleSeedSubmit(payload) {
    if (!game) return;
    setSeedBusy(true);
    setError('');
    try {
      setSeedPreferences(payload);
      await submitSeedPreferences(
        game.id,
        payload.likes,
        payload.dislikes,
        payload.like_product_ids || [],
        payload.dislike_product_ids || [],
      );
      const onboardingPayload = await getOnboarding(game.id);
      setOnboarding(onboardingPayload);
      setView(VIEW.ONBOARDING);
    } catch (seedError) {
      setSeedPreferences(null);
      setError(seedError.message || 'Could not save your preference signals.');
    } finally {
      setSeedBusy(false);
    }
  }

  async function handleSeedSkip() {
    if (!game) return;
    setError('');
    try {
      const onboardingPayload = await getOnboarding(game.id);
      setOnboarding(onboardingPayload);
      setView(VIEW.ONBOARDING);
    } catch (skipError) {
      setError(skipError.message || 'Could not load onboarding.');
    }
  }

  async function handleSubmitRoundPick() {
    if (!game || !roundData || !selectedRoundPick) return;
    setBusy((previous) => ({ ...previous, pick: true }));
    setError('');
    try {
      const result = await submitRoundPick(game.id, roundData.round_number, selectedRoundPick, lessLikeIds);
      const hiddenPreferenceNames = (result.ai_explanation?.hidden_preferences || [])
        .map(([name]) => String(name || '').trim().toLowerCase())
        .filter(Boolean);
      const hiddenHints = result.ai_explanation?.hidden_preference_hints || [];
      const seenHiddenSet = new Set(seenHiddenPreferenceNames);
      const previousHiddenSet = new Set(previousHiddenPreferenceNames);
      const recurringHiddenPreferenceNames = hiddenPreferenceNames.filter((name) => previousHiddenSet.has(name));
      const hasNewRecurringHiddenPreference = recurringHiddenPreferenceNames.some((name) => !seenHiddenSet.has(name));
      const hiddenPreferenceDetected = (
        result.round_number >= 4
        && hiddenHints.length > 0
        && hasNewRecurringHiddenPreference
      );

      setRoundResult({
        ...result,
        hidden_preference_detected: hiddenPreferenceDetected,
      });
      setSeenHiddenPreferenceNames((previous) => {
        const merged = new Set(previous);
        if (hiddenPreferenceDetected) {
          recurringHiddenPreferenceNames.forEach((name) => merged.add(name));
        }
        return [...merged];
      });
      setPreviousHiddenPreferenceNames(hiddenPreferenceNames);
      applyGameProgress(result);
      setView(VIEW.RESULT);
    } catch (pickError) {
      setError(pickError.message || 'Could not submit your pick.');
    } finally {
      setBusy((previous) => ({ ...previous, pick: false }));
    }
  }

  async function handleRefreshRound() {
    if (!game) return;
    setRefreshing(true);
    setError('');
    try {
      const refreshedRound = await refreshRound(game.id, lessLikeIds);
      setRoundData(refreshedRound);
      applyGameProgress(refreshedRound);
      setSelectedRoundPick('');
      setLessLikeIds([]);
    } catch (refreshError) {
      setError(refreshError.message || 'Could not refresh the round.');
    } finally {
      setRefreshing(false);
    }
  }

  async function handleResultNext() {
    if (!game || !roundResult) return;
    setBusy((previous) => ({ ...previous, next: true }));
    setError('');
    try {
      if (roundResult.game_complete) {
        const board = await getLeaderboard(10, activeCategory);
        setLeaderboard(board);
        setView(VIEW.FINAL);
      } else {
        await loadNextRound(game.id);
      }
    } catch (nextError) {
      setError(nextError.message || 'Could not continue.');
    } finally {
      setBusy((previous) => ({ ...previous, next: false }));
    }
  }

  async function handleRemovePreference(productId) {
    if (!game || !roundData) return;
    const currentIds = (roundData.preference_deck || []).map((item) => item.id);
    const nextIds = currentIds.filter((id) => id !== productId);
    setPreferenceBusyId(productId);
    setError('');
    try {
      const updated = await updatePreferences(game.id, nextIds);
      applyGameProgress(updated);
      setRoundData((previous) => {
        if (!previous) return previous;
        if (updated.round) return updated.round;
        return {
          ...previous,
          preference_deck: updated.preference_deck,
          current_match_streak: updated.current_match_streak,
          longest_match_streak: updated.longest_match_streak,
          match_streak_target: updated.match_streak_target,
          rounds_played: updated.rounds_played,
        };
      });
      setRoundResult((previous) => {
        if (!previous) return previous;
        return {
          ...previous,
          preference_deck: updated.preference_deck,
          current_match_streak: updated.current_match_streak,
          longest_match_streak: updated.longest_match_streak,
          match_streak_target: updated.match_streak_target,
          rounds_played: updated.rounds_played,
        };
      });
      setSelectedRoundPick('');
    } catch (preferenceError) {
      setError(preferenceError.message || 'Could not update your preference deck.');
    } finally {
      setPreferenceBusyId('');
    }
  }

  async function handlePlayAgain() {
    if (!playerName.trim()) return;
    await handleStart(true);
  }

  return (
    <main className="app-shell">
      <header className={`app-shell__header ${isAuthenticated ? 'authenticated' : 'public'} ${homeHeader ? 'app-shell__header--home' : 'app-shell__header--blurred'}`}>
        {showHeaderBrand ? (
          <button
            type="button"
            className="brand-home"
            onClick={() => {
              if (isAuthenticated) resetAll();
            }}
            aria-label="Go home"
          >
            <img src={activeLogo} alt="Recommendle" className="app-logo" />
          </button>
        ) : (
          <div className="app-shell__brand-spacer" aria-hidden="true" />
        )}
        <div className="app-shell__actions">
          {isAuthenticated && (view === VIEW.ONBOARDING || view === VIEW.ROUND) && (
            <BrainModePanel
              mode={mode}
              onModeChange={setMode}
              categoryCopy={onboarding?.category_copy || roundData?.category_copy || {}}
            />
          )}
          <button
            type="button"
            className="icon-button"
            onClick={toggleTheme}
            aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
            title={theme === 'light' ? 'Dark mode' : 'Light mode'}
          >
            {theme === 'light' ? <DarkModeOutlinedIcon fontSize="small" /> : <LightModeOutlinedIcon fontSize="small" />}
          </button>
          {isAuthenticated && (
            <AccountMenu
              displayName={displayName}
              username={username}
              isAdmin={userRole === 'admin'}
              onOpenAdmin={() => setView(VIEW.ADMIN)}
              onLogout={handleLogout}
              loading={busy.auth}
            />
          )}
        </div>
      </header>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button type="button" className="ghost" onClick={() => setError('')}>Dismiss</button>
        </div>
      )}

      {!isAuthenticated ? (
        <AuthScreen
          logoSrc={activeLogo}
          onLoginSuccess={handleLoginSuccess}
          loading={busy.auth}
          error=""
        />
      ) : (
        <>
          {view === VIEW.WELCOME && (
            <WelcomeScreen
              logoSrc={activeLogo}
              playerName={playerName}
              setPlayerName={setPlayerName}
              accountDisplayName={displayName}
              isAuthenticated={isAuthenticated}
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
              readyCategoryCount={activeCategoryCount}
              leaderboard={leaderboard}
              onViewPlayer={(name) => setViewingPlayer(name)}
            />
          )}

          {view === VIEW.SEED && (
            <BetaSeedScreen
              category={activeCategory}
              onSkip={handleSeedSkip}
              onSubmit={handleSeedSubmit}
              loading={seedBusy}
            />
          )}

          {view === VIEW.ONBOARDING && onboarding && (
            <>
              <OnboardingGrid
                products={onboarding.products}
                selectedIds={selectedIds}
                onToggle={handleToggleOnboarding}
                onOpenRating={() => setRatingModalOpen(true)}
                onRefresh={handleRefreshOnboarding}
                refreshing={refreshingOnboarding}
                mode={mode}
                categoryCopy={onboarding.category_copy || {}}
                seedPreferences={seedPreferences}
              />
              <SetRatingModal
                open={ratingModalOpen}
                rating={rating}
                setRating={setRating}
                loading={busy.onboarding}
                onClose={() => setRatingModalOpen(false)}
                onSubmit={handleSubmitOnboarding}
                categoryCopy={onboarding.category_copy || {}}
              />
            </>
          )}

          {view === VIEW.ROUND && (
            <RoundArena
              round={roundData}
              mode={mode}
              selectedPick={selectedRoundPick}
              onSelectPick={setSelectedRoundPick}
              onSubmitPick={handleSubmitRoundPick}
              lessLikeIds={lessLikeIds}
              onToggleLessLike={(id) => {
                setLessLikeIds((previous) => (
                  previous.includes(id)
                    ? previous.filter((item) => item !== id)
                    : [...previous, id]
                ));
              }}
              onRefresh={handleRefreshRound}
              refreshing={refreshing}
              submitting={busy.pick}
              onRemovePreference={handleRemovePreference}
              preferenceBusyId={preferenceBusyId}
            />
          )}

          {view === VIEW.RESULT && (
            <RoundResultPanel
              result={roundResult}
              categoryCopy={roundResult?.category_copy || {}}
              mode={mode}
              onNext={handleResultNext}
              loadingNext={busy.next}
            />
          )}

          {view === VIEW.FINAL && (
            <FinalSummary
              playerName={playerName}
              category={activeCategory}
              gameId={game?.id}
              leaderboard={leaderboard}
              onRestart={handlePlayAgain}
              onViewPlayer={(name) => setViewingPlayer(name)}
            />
          )}

          {view === VIEW.ADMIN && userRole === 'admin' && (
            <AdminScreen onBack={() => setView(VIEW.WELCOME)} />
          )}

          {viewingPlayer && (
            <PlayerStatsModal
              playerName={viewingPlayer}
              category={activeCategory}
              onClose={() => setViewingPlayer(null)}
            />
          )}
        </>
      )}
    </main>
  );
}
