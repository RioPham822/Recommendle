import { useState } from 'react';
import './AccountMenu.css';

export default function AccountMenu({
  displayName,
  username,
  onLogout,
  loading,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

  const handleLogout = () => {
    setIsOpen(false);
    onLogout();
  };

  return (
    <div className="account-menu-container">
      <button
        className="account-button"
        onClick={() => setIsOpen(!isOpen)}
        title="Account menu"
        disabled={loading}
      >
        <span className="account-icon">👤</span>
        <span className="account-name">{displayName}</span>
        <span className={`account-chevron ${isOpen ? 'open' : ''}`}>▼</span>
      </button>

      {isOpen && (
        <div className="account-menu">
          <div className="account-info">
            <p className="account-info-name">{displayName}</p>
            <p className="account-info-username">@{username}</p>
          </div>

          <div className="account-divider"></div>

          <button
            className="account-menu-item logout-item"
            onClick={() => setShowLogoutConfirm(true)}
            disabled={loading}
          >
            <span>🚪</span>
            <span>Sign Out</span>
          </button>

          {showLogoutConfirm && (
            <div className="logout-confirm">
              <p>Sign out?</p>
              <div className="logout-confirm-buttons">
                <button
                  onClick={handleLogout}
                  disabled={loading}
                  className="confirm-yes"
                >
                  Yes
                </button>
                <button
                  onClick={() => setShowLogoutConfirm(false)}
                  disabled={loading}
                  className="confirm-no"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {isOpen && (
        <div
          className="account-menu-backdrop"
          onClick={() => setIsOpen(false)}
        ></div>
      )}
    </div>
  );
}
