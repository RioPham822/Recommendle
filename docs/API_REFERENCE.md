# API Reference - Authentication & Database Tools

## Quick Reference

### Authentication Endpoints
All endpoints return JSON responses.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login & get session token |
| GET | `/api/auth/user/{user_id}` | Get user info |
| POST | `/api/auth/change-password` | Change password |
| POST | `/api/auth/logout` | Logout (invalidate token) |

---

## Database Export Command Reference

### Interactive Mode
```bash
cd backend
python test.py
```

Then select from menu:
- **7** - Export Local Database to Excel
- **8** - Export Atlas (Cloud) Database to Excel
- **9** - Export Specific Local Collection
- **10** - Export Specific Cloud Collection
- **11** - Local Database Summary
- **12** - Cloud Database Summary

### Command-Line Mode

| Command | Description |
|---------|-------------|
| `python test.py export-local` | Export all local collections to CSV |
| `python test.py export-atlas` | Export all cloud collections to CSV |
| `python test.py export-local-collection products` | Export specific local collection |
| `python test.py export-atlas-collection games` | Export specific cloud collection |
| `python test.py sync-local-to-atlas` | Upload local → cloud |
| `python test.py sync-atlas-to-local` | Download cloud → local |
| `python test.py view-local` | View all local data (JSON) |
| `python test.py summary-local` | Count documents in local DB |

---

## Authentication Examples

### 1. Register User
```bash
curl -X POST http://localhost:8015/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "MyPassword123",
    "display_name": "Alice Smith"
  }'
```

**Response:**
```json
{
  "user_id": "507f1f77bcf86cd799439011",
  "username": "alice",
  "display_name": "Alice Smith",
  "session_token": "xB9kL2pQ7tF4mN8vR...",
  "expires_at": "2026-02-26T12:00:00"
}
```

### 2. Login User
```bash
curl -X POST http://localhost:8015/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "MyPassword123"
  }'
```

### 3. Get User Profile
```bash
curl http://localhost:8015/api/auth/user/507f1f77bcf86cd799439011
```

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "username": "alice",
  "display_name": "Alice Smith",
  "created_at": "2026-02-19T10:30:00"
}
```

### 4. Change Password
```bash
curl -X POST http://localhost:8015/api/auth/change-password \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "MyPassword123",
    "new_password": "NewPassword456"
  }' \
  -H "Authorization: Bearer xB9kL2pQ7tF4mN8vR..."
```

### 5. Logout
```bash
curl -X POST http://localhost:8015/api/auth/logout \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "507f1f77bcf86cd799439011",
    "session_token": "xB9kL2pQ7tF4mN8vR..."
  }'
```

---

## Frontend Integration

### Store Auth Info (after login)
```javascript
// Upon successful login/register
localStorage.setItem('userId', response.user_id);
localStorage.setItem('sessionToken', response.session_token);
localStorage.setItem('displayName', response.display_name);
localStorage.setItem('tokenExpiry', response.expires_at);
```

### Use Auth in API Calls
```javascript
const headers = {
  'Content-Type': 'application/json',
};

if (localStorage.getItem('sessionToken')) {
  headers['Authorization'] = `Bearer ${localStorage.getItem('sessionToken')}`;
}

// Then in fetch requests
fetch(url, { method: 'POST', headers, body: JSON.stringify(...) })
```

### Check Token Expiry
```javascript
function isTokenExpired() {
  const expiry = new Date(localStorage.getItem('tokenExpiry'));
  return new Date() > expiry;
}
```

### Logout (clear storage)
```javascript
localStorage.removeItem('userId');
localStorage.removeItem('sessionToken');
localStorage.removeItem('displayName');
localStorage.removeItem('tokenExpiry');
// Redirect to login screen
```

---

## Database Schema

### Users Collection
```javascript
{
  _id: ObjectId,
  username: String (unique, lowercase),
  password_hash: String,
  display_name: String,
  created_at: Date,
  updated_at: Date,
  games: [ObjectId],  // References to game documents
  session_tokens: [
    {
      token: String,
      created_at: Date,
      expires_at: Date,
      ip_address: String
    }
  ]
}
```

### Games Collection (after auth integration)
```javascript
{
  _id: ObjectId,
  player_name: String,
  user_id: ObjectId,  // NEW: Reference to user
  category: String,
  status: String,
  total_rounds: Number,
  human_score: Number,
  ai_score: Number,
  created_at: Date,
  updated_at: Date
}
```

---

## Common Issues & Solutions

### Q: "Username already exists"
- Choose a different username
- Username is case-insensitive (alice = ALICE = Alice)

### Q: "Invalid username or password" on login
- Check spelling of username (case-insensitive)
- Password is case-sensitive
- Minimum 6 characters required

### Q: "Session token expired"
- User was logged in for 7+ days
- Implement re-login on frontend when token expires
- Check `isTokenExpired()` before making authenticated requests

### Q: CSV export file is empty
- Ensure MongoDB is running and contains data
- Run `python test.py summary-local` to check document counts
- Check that collection names are spelled correctly

### Q: CORS error when making auth requests
- CORS is configured for localhost:5173 and Render
- If using different origin, update `allowed_origins` in `main.py`

---

## Security Best Practices

✅ **DO:**
- Store `session_token` in secure httpOnly cookies (recommended)
- Validate tokens on backend for protected endpoints
- Clear tokens on logout
- Use HTTPS in production
- Expire tokens after inactivity

❌ **DON'T:**
- Send passwords in URLs
- Store passwords in localStorage (only tokens)
- Log or expose session tokens
- Reuse tokens across devices/sessions
- Allow session tokens to persist forever

---

## Configuration

Edit `backend/app/db.py` to change:
```python
# Session expiry time
TOKEN_EXPIRY_DAYS = 7

# MongoDB URLs
MONGODB_URL = "mongodb://localhost:27017"  # Local
ATLAS_URL = "mongodb+srv://..."            # Cloud
```

Edit `backend/app/services/auth.py` to change:
```python
# Password hashing iterations (higher = more secure but slower)
hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), ..., 100000)
```

---

## Troubleshooting

### Check local data was exported
```bash
ls -la ./data/exports/
```

### View exported data
```bash
cat ./data/exports/products.csv
# Or open in Excel
```

### Check user was created
```bash
python test.py view-local-collection users
```

### Verify MongoDB connection
```bash
python -c "from motor.motor_asyncio import AsyncIOMotorClient; import asyncio; asyncio.run(AsyncIOMotorClient('mongodb://localhost:27017').admin.command('ping'))"
```

