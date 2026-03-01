import { useState } from 'react';
import './AuthScreen.css';

export default function AuthScreen({
  logoSrc,
  onLoginSuccess,
  loading,
  error,
}) {
  const [mode, setMode] = useState('login'); // 'login' or 'register'
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [localError, setLocalError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError(null);

    // Validation
    if (!username.trim()) {
      setLocalError('Username is required');
      return;
    }
    if (username.length < 3) {
      setLocalError('Username must be at least 3 characters');
      return;
    }
    if (!password) {
      setLocalError('Password is required');
      return;
    }
    if (password.length < 6) {
      setLocalError('Password must be at least 6 characters');
      return;
    }

    if (mode === 'register') {
      if (password !== confirmPassword) {
        setLocalError('Passwords do not match');
        return;
      }
      if (!displayName.trim()) {
        setLocalError('Display name is required');
        return;
      }
    }

    setIsLoading(true);

    try {
      const endpoint = mode === 'login' ? '/api/auth/login' : '/api/auth/register';
      const payload =
        mode === 'login'
          ? { username: username.trim(), password }
          : {
              username: username.trim(),
              password,
              display_name: displayName.trim(),
            };

      const response = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8015'}${endpoint}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || 'Authentication failed');
      }

      const data = await response.json();

      // Store auth info
      localStorage.setItem('userId', data.user_id);
      localStorage.setItem('sessionToken', data.session_token);
      localStorage.setItem('displayName', data.display_name);
      localStorage.setItem('username', data.username);
      localStorage.setItem('tokenExpiry', data.expires_at);

      // Call success callback
      onLoginSuccess({
        userId: data.user_id,
        username: data.username,
        displayName: data.display_name,
        sessionToken: data.session_token,
      });
    } catch (err) {
      setLocalError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const displayError = localError || error;

  return (
    <section className="screen shell auth-screen">
      <div className="auth-container">
        <div className="auth-box">
          <div className="auth-header">
            <img src={logoSrc} alt="Recommendle" className="auth-logo" />
            <h1>{mode === 'login' ? 'Welcome Back' : 'Join the Game'}</h1>
            <p className="auth-subtitle">
              {mode === 'login'
                ? 'Sign in to your account to play'
                : 'Create your account to start playing'}
            </p>
          </div>

          <form onSubmit={handleSubmit} className="auth-form">
            {displayError && <div className="auth-error">{displayError}</div>}

            <div className="form-group">
              <label htmlFor="username">Username</label>
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Choose a unique username"
                disabled={isLoading || loading}
                minLength={3}
                maxLength={80}
              />
              <small>3-80 characters</small>
            </div>

            {mode === 'register' && (
              <div className="form-group">
                <label htmlFor="display-name">Display Name</label>
                <input
                  id="display-name"
                  type="text"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  placeholder="Name shown on leaderboards"
                  disabled={isLoading || loading}
                  maxLength={100}
                />
                <small>How you appear to other players</small>
              </div>
            )}

            <div className="form-group">
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Create a secure password"
                disabled={isLoading || loading}
                minLength={6}
                maxLength={200}
              />
              <small>At least 6 characters</small>
            </div>

            {mode === 'register' && (
              <div className="form-group">
                <label htmlFor="confirm-password">Confirm Password</label>
                <input
                  id="confirm-password"
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Re-enter your password"
                  disabled={isLoading || loading}
                  minLength={6}
                  maxLength={200}
                />
              </div>
            )}

            <button
              type="submit"
              disabled={isLoading || loading}
              className="auth-submit-button"
            >
              {isLoading || loading ? 'Processing...' : mode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>

          <div className="auth-toggle">
            <p>
              {mode === 'login' ? "Don't have an account?" : 'Already have an account?'}
              <button
                type="button"
                onClick={() => {
                  setMode(mode === 'login' ? 'register' : 'login');
                  setLocalError(null);
                  setUsername('');
                  setPassword('');
                  setConfirmPassword('');
                  setDisplayName('');
                }}
                disabled={isLoading || loading}
                className="toggle-button"
              >
                {mode === 'login' ? 'Sign Up' : 'Sign In'}
              </button>
            </p>
          </div>

          <div className="auth-info">
            <h3>🎮 How it works:</h3>
            <ul>
              <li>Create an account or sign in</li>
              <li>Pick a category and rate 10 items</li>
              <li>Battle AI in 5 rounds of predictions</li>
              <li>Your scores are saved to your account</li>
              <li>Compete on the leaderboard</li>
            </ul>
          </div>
        </div>

        <div className="auth-background">
          <div className="background-shape shape-1"></div>
          <div className="background-shape shape-2"></div>
          <div className="background-shape shape-3"></div>
        </div>
      </div>
    </section>
  );
}
