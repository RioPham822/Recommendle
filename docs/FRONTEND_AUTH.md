# Authentication Frontend Implementation

## Overview

A complete user authentication system with login/register screens has been integrated into the frontend. Players must create an account to play independently.

## New Components

### 1. **AuthScreen.jsx** - Login/Register Screen
- Professional login and registration form
- Mode toggle between login and signup
- Client-side validation
- Error handling with user feedback
- Auto-login after registration
- Form fields:
  - Username (3-80 chars)
  - Password (min 6 chars)
  - Display Name (for leaderboards)
  - Confirm Password (on signup)

### 2. **AccountMenu.jsx** - User Profile Dropdown
- Top-right account menu button
- Shows player's display name
- Dropdown with user info
- Sign out button with confirmation
- Responsive design (icon-only on mobile)

## Updated Files

### **App.jsx** - Main App Component
- Authentication state management
- Shows AuthScreen when not authenticated
- Conditional rendering of game screens based on auth status
- Account menu in header when logged in
- Logout functionality
- Auto-login persistent session from localStorage

### **api.js** - API Module
Added functions:
```javascript
registerUser(username, password, displayName)
loginUser(username, password)
getUser(userId)
changePassword(userId, oldPassword, newPassword, sessionToken)
logoutUser(userId, sessionToken)
getAuthToken()
getUserId()
getDisplayName()
getUsername()
isTokenExpired()
clearAuthData()
```

### **styles.css** - Global Styles
- App header styling with account menu support
- Responsive header design
- Dark mode support

## Styling

### AuthScreen.css
- Modern gradient background
- Animated decorative shapes
- Smooth form transitions
- Error message styling
- Mobile responsive (responsive buttons, fonts, spacing)
- Dark mode support

### AccountMenu.css
- Dropdown menu animation
- Profile info display
- Logout confirmation dialog
- Responsive dropdown (mobile: fixed bottom sheet)
- Accessibility features

## User Flow

### First Time Player
1. Land on AuthScreen
2. Click "Sign Up"
3. Enter username, password, display name
4. Auto-login after registration
5. Choose category and play

### Returning Player
1. Land on AuthScreen
2. Enter username and password
3. Click "Sign In"
4. Redirected to game selection
5. Play with persistent profile

### Session Management
- Session stored in localStorage
- Token includes 7-day expiry
- Auto-logout on token expiration
- Manual logout available in account menu
- All data cleared on logout

## Storage

Auth data saved to localStorage:
```javascript
localStorage.setItem('userId', response.user_id);
localStorage.setItem('sessionToken', response.session_token);
localStorage.setItem('displayName', response.display_name);
localStorage.setItem('username', response.username);
localStorage.setItem('tokenExpiry', response.expires_at);
```

## Security Features

✅ Passwords validated client-side (min 6 chars)
✅ Session tokens stored (not passwords)
✅ Token expiry checked before requests
✅ Logout clears all auth data
✅ HTTPS ready (configured in backend)

## Responsive Design

### Desktop
- Full width login form
- Dropdown account menu
- Side-by-side header with logo and account

### Tablet (640px - 1024px)
- Responsive form width
- Adjusted padding and spacing
- Account name visible in menu

### Mobile (< 640px)
- 100% width forms
- Fixed bottom sheet for dropdown menu
- Icon-only account button
- Larger tap targets (accessibility)
- Font size 16px to prevent zoom

## Testing

To test the authentication:

1. **Register new user:**
   - Click "Sign Up" tab
   - Username: testuser
   - Password: test123
   - Display Name: Test Player
   - Click "Create Account"

2. **Login:**
   - Click "Sign In" tab
   - Username: testuser
   - Password: test123
   - Click "Sign In"

3. **Game flow:**
   - Select category
   - Play game normally
   - Your display name appears as player

4. **Logout:**
   - Click account menu (top right)
   - Click "Sign Out"
   - Confirm logout
   - Redirected to login screen

## Integration Notes

### For Game Endpoints
Current game endpoints use `player_name` field. When integrating with authenticated users:
- Player name defaults to display_name from localStorage
- Can be overridden if needed
- Recommend adding `user_id` to game creation in the future

### For API Calls
Auth info is available via:
```javascript
import {
  getAuthToken,
  getUserId,
  getDisplayName,
  getUsername,
} from './lib/api';

// Use in authenticated requests
const token = getAuthToken();
const userId = getUserId();
```

### For Custom Styling
Use CSS variables from styles.css:
```css
--color-accent: #6366f1
--color-text-primary: (dark/light adjusted)
--color-text-secondary: (muted text)
--color-panel-bg: (background)
--color-border: (borders)
--color-error: #ef4444
```

## Browser Compatibility

- Modern browsers (Chrome, Firefox, Safari, Edge)
- ES6+ JavaScript
- CSS Grid and Flexbox
- LocalStorage API
- Fetch API

## Future Enhancements

1. **Password Reset**
   - Email verification link
   - Temporary reset token

2. **Multi-Device Sessions**
   - Multiple active tokens per user
   - Device management dashboard

3. **User Statistics**
   - View all personal game history
   - Win/loss ratios per category
   - Preference patterns

4. **Social Features**
   - Add friends
   - Compare scores
   - Challenges

5. **Profile Customization**
   - Avatar/profile picture
   - Bio
   - Preferred categories

## File Structure

```
frontend/src/
├── components/
│   ├── AuthScreen.jsx          ✅ NEW
│   ├── AuthScreen.css          ✅ NEW
│   ├── AccountMenu.jsx         ✅ NEW
│   ├── AccountMenu.css         ✅ NEW
│   ├── App.jsx                 ✅ UPDATED
│   └── ... (other components)
├── lib/
│   └── api.js                  ✅ UPDATED
├── styles.css                  ✅ UPDATED
└── ...
```

## Debugging

Enable debug logs:
```javascript
// In components
console.log('Auth state:', { isAuthenticated, displayName, username });
console.log('Token valid:', !isTokenExpired());
console.log('User ID:', getUserId());
```

Check localStorage:
```javascript
console.log(localStorage);
```

Verify API response in browser DevTools Network tab:
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
