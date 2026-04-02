import { useState } from 'react';
import './AuthScreen.css';

export default function AuthScreen({
  logoSrc,
  onLoginSuccess,
  loading,
  error,
}) {
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [localError, setLocalError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    setLocalError('');

    if (!username.trim()) {
      setLocalError('Username is required.');
      return;
    }
    if (username.trim().length < 3) {
      setLocalError('Username must be at least 3 characters.');
      return;
    }
    if (!password) {
      setLocalError('Password is required.');
      return;
    }
    if (password.length < 6) {
      setLocalError('Password must be at least 6 characters.');
      return;
    }
    if (mode === 'register') {
      if (!displayName.trim()) {
        setLocalError('Display name is required.');
        return;
      }
      if (password !== confirmPassword) {
        setLocalError('Passwords do not match.');
        return;
      }
    }

    setIsLoading(true);
    try {
      const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const payload = mode === 'login'
        ? { username: username.trim(), password }
        : { username: username.trim(), password, display_name: displayName.trim() };

      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8015'}${endpoint}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      );

      if (!response.ok) {
        const errorPayload = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorPayload.detail || 'Authentication failed.');
      }

      const data = await response.json();
      localStorage.setItem('userId', data.user_id);
      localStorage.setItem('sessionToken', data.session_token);
      localStorage.setItem('displayName', data.display_name);
      localStorage.setItem('username', data.username);
      localStorage.setItem('userRole', data.role || 'player');
      localStorage.setItem('tokenExpiry', data.expires_at);

      onLoginSuccess({
        userId: data.user_id,
        username: data.username,
        role: data.role || 'player',
        displayName: data.display_name,
        sessionToken: data.session_token,
      });
    } catch (submissionError) {
      setLocalError(submissionError.message || 'Authentication failed.');
    } finally {
      setIsLoading(false);
    }
  }

  const displayError = localError || error;

  function resetMode(nextMode) {
    setMode(nextMode);
    setUsername('');
    setPassword('');
    setConfirmPassword('');
    setDisplayName('');
    setLocalError('');
  }

  return (
    <section className="screen shell auth-screen">
      <div className="auth-screen__stage">
        <div className="auth-screen__copy">
          <img src={logoSrc} alt="Recommendle" className="auth-screen__logo" />
          <p className="eyebrow">Train the model</p>
          <h1>Can AI read your mind?</h1>
          <p className="auth-screen__lede">
            Build your taste profile, tune the AI with a few signals up front, and see how quickly it learns to choose like you.
          </p>
        </div>

        <div className="auth-card">
          <div className="auth-card__header">
            <h2>{mode === 'login' ? 'Sign in' : 'Create account'}</h2>
            <p>
              {mode === 'login'
                ? 'Pick up where you left off.'
                : 'Your saved runs and leaderboard history stay tied to this account.'}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            {displayError && <div className="auth-error">{displayError}</div>}

            <label className="auth-field">
              <span>Username</span>
              <input
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="your-name"
                maxLength={80}
                minLength={3}
                disabled={isLoading || loading}
              />
            </label>

            {mode === 'register' && (
              <label className="auth-field">
                <span>Display name</span>
                <input
                  type="text"
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  placeholder="What shows on the leaderboard"
                  maxLength={100}
                  disabled={isLoading || loading}
                />
              </label>
            )}

            <label className="auth-field">
              <span>Password</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="At least 6 characters"
                maxLength={200}
                minLength={6}
                disabled={isLoading || loading}
              />
            </label>

            {mode === 'register' && (
              <label className="auth-field">
                <span>Confirm password</span>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder="Re-enter your password"
                  maxLength={200}
                  minLength={6}
                  disabled={isLoading || loading}
                />
              </label>
            )}

            <button type="submit" className="auth-submit-button" disabled={isLoading || loading}>
              {isLoading || loading
                ? 'Processing...'
                : mode === 'login'
                  ? 'Enter Recommendle'
                  : 'Create account'}
            </button>
          </form>

          <div className="auth-card__toggle">
            <span>{mode === 'login' ? "Need an account?" : 'Already have an account?'}</span>
            <button
              type="button"
              className="toggle-button"
              onClick={() => resetMode(mode === 'login' ? 'register' : 'login')}
              disabled={isLoading || loading}
            >
              {mode === 'login' ? 'Sign up' : 'Sign in'}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
