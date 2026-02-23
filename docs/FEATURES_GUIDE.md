# New Features - Excel Export & User Authentication

## 1. Excel/CSV Data Export

### Interactive Mode
Run the test.py script and select options 7-10:

```bash
cd backend
python test.py
```

Then choose:
- **Option 7**: Export Local Database to Excel
- **Option 8**: Export Atlas (Cloud) Database to Excel
- **Option 9**: Export Specific Collection from Local (e.g., "products", "users", "games")
- **Option 10**: Export Specific Collection from Atlas

All CSV files are saved to `./data/exports/` and can be opened with Excel, Google Sheets, or any spreadsheet application.

### Command-line Mode

Export all local collections:
```bash
python test.py export-local
```

Export all cloud collections:
```bash
python test.py export-atlas
```

Export a specific collection:
```bash
python test.py export-local-collection products
python test.py export-atlas-collection games
```

### What Gets Exported
- All MongoDB collections are converted to CSV format
- ObjectIds are converted to strings
- DateTime fields are converted to ISO format
- Nested objects and arrays are preserved as JSON strings
- All files are saved with proper UTF-8 encoding

---

## 2. User Authentication System

Multiple players can now create accounts and play independently with secure username/password login.

### API Endpoints

#### Register New User
```bash
POST /api/auth/register
Content-Type: application/json

{
  "username": "john_doe",
  "password": "securePassword123",
  "display_name": "John Doe"  # Optional, defaults to username
}
```

Response:
```json
{
  "user_id": "507f1f77bcf86cd799439011",
  "username": "john_doe",
  "display_name": "John Doe",
  "session_token": "ABC123...",
  "expires_at": "2026-02-26T12:00:00"
}
```

#### Login
```bash
POST /api/auth/login
Content-Type: application/json

{
  "username": "john_doe",
  "password": "securePassword123"
}
```

Returns the same response as register.

#### Get User Info
```bash
GET /api/auth/user/{user_id}
```

Returns user details (without password).

#### Change Password
```bash
POST /api/auth/change-password
Content-Type: application/json

{
  "old_password": "currentPassword",
  "new_password": "newPassword123"
}
```

#### Logout
```bash
POST /api/auth/logout

{
  "user_id": "507f1f77bcf86cd799439011",
  "session_token": "ABC123..."
}
```

### Frontend Implementation (Next Steps)

You'll want to update the frontend to:

1. **Add Login/Register Screen**
   - Replace or enhance WelcomeScreen to show auth options first
   - Store `session_token` and `user_id` in localStorage

2. **Update Game Start**
   - Change game creation to use authenticated user_id instead of just player_name
   - Pass session_token in headers for authenticated requests

3. **Update API Calls**
   ```javascript
   // Store after login
   localStorage.setItem('user_id', response.user_id);
   localStorage.setItem('session_token', response.session_token);
   
   // Use in requests
   const headers = {
     'Content-Type': 'application/json',
     'Authorization': `Bearer ${localStorage.getItem('session_token')}`,
   };
   ```

### Database Schema

Users are stored in the `users` collection with:
- `username` (unique, lowercase, indexed)
- `password_hash` (salted + hashed with PBKDF2)
- `display_name` (for leaderboards)
- `session_tokens` (list of active sessions with expiry)
- `games` (list of game IDs they've played)

### Security Features

✅ Passwords hashed with PBKDF2 (100,000 iterations)
✅ Unique usernames (case-insensitive)
✅ Session tokens have 7-day expiry
✅ Secure token generation with secrets module
✅ Invalid credentials return generic error message

### Multiple Players

Now multiple people can play independently:

1. **User A** registers as "alice" → plays 5 games
2. **User B** registers as "bob" → plays 10 games
3. Each user has their own game history and leaderboard stats
4. Games are linked to user accounts (not just player_name)

---

## 3. Updated Game Flow

### Current (Without Auth)
```
Player enters name → Picks category → Plays game
```

### New (With Auth) - Recommended
```
Register/Login → Player authenticated → Pick category → Plays game
→ Game linked to user account → History saved per user
```

### Gradual Migration

You can keep the old system working while adding auth features:
- Games can still use just `player_name` (backward compatible)
- New games created by authenticated users link to their `user_id`
- Games table can have optional `user_id` field

---

## Example: Complete Game Flow with Auth

### 1. Register
```bash
curl -X POST http://localhost:8015/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "mysecurepass",
    "display_name": "Alice Smith"
  }'
```

### 2. Start Game with User
```bash
curl -X POST http://localhost:8015/api/game/start \
  -H "Content-Type: application/json" \
  -d '{
    "player_name": "alice",
    "user_id": "507f1f77bcf86cd799439011",
    "category": "fountain_pens"
  }' \
  -H "Authorization: Bearer SESSION_TOKEN"
```

### 3. Get User's Game History
```bash
curl http://localhost:8015/api/game/player/alice/history \
  -H "Authorization: Bearer SESSION_TOKEN"
```

---

## Database Management

Both new features work seamlessly with the existing database tools:

### Sync with Auth Data
```bash
python test.py sync-local-to-atlas      # Syncs users, games, products
python test.py export-local              # Exports all including users
```

### View Users
```bash
python test.py view-local-collection users
```

---

## Configuration

Settings are in `backend/app/db.py`:

```python
# Session token expiry (default: 7 days)
TOKEN_EXPIRY_DAYS = 7

# Password hashing iterations (default: 100,000)
# Found in services/auth.py
```

---

## Next Steps

1. ✅ Excel export added
2. ✅ Auth system added
3. 🔄 Update frontend to use authentication
4. 🔄 Link games to authenticated users
5. 🔄 Add password reset functionality (optional)
6. 🔄 Add email verification (optional)

