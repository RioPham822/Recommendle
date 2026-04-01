import { useEffect, useRef, useState } from 'react';
import AdminPanelSettingsRoundedIcon from '@mui/icons-material/AdminPanelSettingsRounded';
import ExpandMoreRoundedIcon from '@mui/icons-material/ExpandMoreRounded';
import LogoutRoundedIcon from '@mui/icons-material/LogoutRounded';
import PersonOutlineRoundedIcon from '@mui/icons-material/PersonOutlineRounded';
import './AccountMenu.css';

export default function AccountMenu({
  displayName,
  username,
  isAdmin,
  onOpenAdmin,
  onLogout,
  loading,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (!menuRef.current) return;
      if (!menuRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }

    function handleEscape(event) {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, []);

  return (
    <div className="account-menu-container" ref={menuRef}>
      <button
        type="button"
        className={`icon-button account-button ${isOpen ? 'open' : ''}`}
        onClick={() => setIsOpen((prev) => !prev)}
        title="Account"
        aria-label="Open account menu"
        aria-expanded={isOpen}
        disabled={loading}
      >
        <PersonOutlineRoundedIcon fontSize="small" />
        <ExpandMoreRoundedIcon fontSize="small" />
      </button>

      {isOpen && (
        <div className="account-menu">
          <div className="account-menu__identity">
            <p className="account-menu__name">{displayName}</p>
            <p className="account-menu__username">@{username}</p>
          </div>
          {isAdmin && (
            <button
              type="button"
              className="account-menu__item"
              onClick={() => {
                setIsOpen(false);
                onOpenAdmin();
              }}
              disabled={loading}
            >
              <AdminPanelSettingsRoundedIcon fontSize="small" />
              <span>Admin workspace</span>
            </button>
          )}
          <button
            type="button"
            className="account-menu__item"
            onClick={() => {
              setIsOpen(false);
              onLogout();
            }}
            disabled={loading}
          >
            <LogoutRoundedIcon fontSize="small" />
            <span>Sign out</span>
          </button>
        </div>
      )}
    </div>
  );
}
