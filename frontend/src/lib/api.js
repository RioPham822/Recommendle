const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8015').replace(/\/$/, '');

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = payload.detail || payload.message || detail;
    } catch {
      // Ignore JSON parsing errors; use status text.
    }
    throw new Error(detail);
  }

  return response.json();
}

// ============ AUTHENTICATION ENDPOINTS ============

export async function registerUser(username, password, displayName) {
  return request('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({
      username,
      password,
      display_name: displayName,
    }),
  });
}

export async function loginUser(username, password) {
  return request('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      username,
      password,
    }),
  });
}

export async function getUser(userId) {
  return request(`/api/auth/user/${userId}`);
}

export async function changePassword(userId, oldPassword, newPassword, sessionToken) {
  return request('/api/auth/change-password', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${sessionToken}`,
    },
    body: JSON.stringify({
      old_password: oldPassword,
      new_password: newPassword,
    }),
  });
}

export async function logoutUser(userId, sessionToken) {
  return request('/api/auth/logout', {
    method: 'POST',
    body: JSON.stringify({
      user_id: userId,
      session_token: sessionToken,
    }),
  });
}

// ============ GAME ENDPOINTS ============

export async function startGame(playerName, category = 'fountain_pens', freshStart = false) {
  return request('/api/game/start', {
    method: 'POST',
    body: JSON.stringify({ player_name: playerName, category, fresh_start: freshStart }),
  });
}

export async function getCategories() {
  return request('/api/game/categories');
}

export async function getResumeState(playerName, category = 'fountain_pens') {
  return request(
    `/api/game/resume-state?player_name=${encodeURIComponent(playerName)}&category=${encodeURIComponent(category)}`,
  );
}

export async function getOnboarding(gameId) {
  return request(`/api/game/${gameId}/onboarding`);
}

export async function submitOnboarding(gameId, selectedProductIds, rating) {
  return request(`/api/game/${gameId}/onboarding/submit`, {
    method: 'POST',
    body: JSON.stringify({
      selected_product_ids: selectedProductIds,
      rating,
    }),
  });
}

export async function startRound(gameId) {
  return request(`/api/game/${gameId}/round/start`, {
    method: 'POST',
  });
}

export async function submitRoundPick(gameId, roundNumber, productId) {
  return request(`/api/game/${gameId}/round/${roundNumber}/pick`, {
    method: 'POST',
    body: JSON.stringify({ product_id: productId }),
  });
}

export async function getGameStatus(gameId) {
  return request(`/api/game/${gameId}/status`);
}

export async function getLeaderboard(limit = 10, category = 'fountain_pens') {
  return request(`/api/game/leaderboard?limit=${limit}&category=${encodeURIComponent(category)}`);
}

export async function getGameSummary(gameId) {
  return request(`/api/game/${gameId}/summary`);
}

export async function getPlayerHistory(playerName, category = 'fountain_pens') {
  return request(
    `/api/game/player/${encodeURIComponent(playerName)}/history?category=${encodeURIComponent(category)}`,
  );
}

// ============ UTILITY FUNCTIONS ============

export function formatPrice(priceMin, priceMax) {
  if (typeof priceMin !== 'number' && typeof priceMax !== 'number') {
    return 'N/A';
  }
  if (typeof priceMin === 'number' && typeof priceMax === 'number' && priceMin !== priceMax) {
    return `$${priceMin.toFixed(0)} - $${priceMax.toFixed(0)}`;
  }
  const value = typeof priceMin === 'number' ? priceMin : priceMax;
  return `$${value.toFixed(0)}`;
}

// ============ AUTH STORAGE HELPERS ============

export function getAuthToken() {
  return localStorage.getItem('sessionToken');
}

export function getUserId() {
  return localStorage.getItem('userId');
}

export function getDisplayName() {
  return localStorage.getItem('displayName');
}

export function getUsername() {
  return localStorage.getItem('username');
}

export function isTokenExpired() {
  const expiry = localStorage.getItem('tokenExpiry');
  if (!expiry) return true;
  return new Date() > new Date(expiry);
}

export function clearAuthData() {
  localStorage.removeItem('userId');
  localStorage.removeItem('sessionToken');
  localStorage.removeItem('displayName');
  localStorage.removeItem('username');
  localStorage.removeItem('tokenExpiry');
}
