# Recommendle

**Recommendle** is an interactive web game where players compete against an AI recommendation engine to predict fountain pen preferences. Built as a senior design project (CSC 492), it explores **sequential preference modeling** — the idea that user taste can be inferred and updated from a sequence of choices rather than traditional single-item ratings.

---

## How It Works

1. **Onboarding** — You're shown a diverse pool of 50 fountain pens. Pick 10 that appeal to you and rate the set.
2. **5 Rounds of Dueling** — Each round presents 10 candidate pens. You pick one; the AI simultaneously predicts which one you'll choose.
3. **Scoring** — Each round awards 10 points to whoever "wins" (match = AI point, miss = human point). The final score tells you how predictable (or surprising) your taste is.
4. **Leaderboard** — Completed games are ranked by score delta across all players.

The AI uses a lightweight **prefix-based collaborative filtering** model that updates its understanding of your preferences after every pick, combining feature-space similarity (vendor, type, nib, price) with the sequential history of your choices.

### Hidden Preference Discovery

After enough rounds, the AI begins detecting **hidden preferences** — features that appear across your selections even though you likely weren't targeting them. For example, you might consistently pick pens that share a vendor or nib size without realizing it.

- **Progressive hints** appear during rounds (typically round 3+) as "Hidden Patterns Emerging" tags.
- **Full reveal at game end** — the Final Summary includes a "Hidden Gems" panel showing:
  - The latent features the AI detected
  - A narrative explanation of the patterns
  - **Pens You Didn't Know You'd Love** — product recommendations scored against only the hidden feature dimensions

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 18 · Vite · Vanilla CSS |
| **Backend** | Python · FastAPI · Uvicorn |
| **Database** | MongoDB (via Motor async driver) |
| **ML Model** | Prefix-based Collaborative Filtering with NMF |
| **Data** | ~500 fountain pens scraped from Goulet Pens |

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main_mongo.py        # FastAPI entry point
│   │   ├── routes/game.py       # Game API endpoints
│   │   ├── services/
│   │   │   ├── game_service.py  # Core game logic & round generation
│   │   │   └── recommender_mongo.py
│   │   ├── ml/
│   │   │   ├── prefix_cf.py     # Prefix-based CF model
│   │   │   └── pbcf_nmf_mongo.py
│   │   ├── models_mongo.py      # Pydantic data models
│   │   └── schemas_game.py      # API request/response schemas
│   ├── data/
│   │   ├── products.json        # Full product catalog
│   │   └── fountain_pens.csv
│   ├── scripts/                 # Data loading & evaluation scripts
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main game state machine
│   │   ├── components/          # UI components
│   │   │   ├── WelcomeScreen.jsx
│   │   │   ├── OnboardingGrid.jsx
│   │   │   ├── SetRatingModal.jsx
│   │   │   ├── RoundArena.jsx
│   │   │   ├── RoundResultPanel.jsx
│   │   │   ├── FinalSummary.jsx
│   │   │   └── BrainModePanel.jsx
│   │   └── lib/api.js           # API client
│   ├── package.json
│   └── vite.config.js
└── docs/
    └── design.md                # Design document
```

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** & npm
- **MongoDB** running locally on the default port (`27017`)

### 1. Clone the repository

```bash
git clone https://github.com/ncstate-csc-sdc/2026Spring-Team42-Decidio-3.git
cd Recommendle
```

### 2. Set up the backend

```bash
cd backend
python -m pip install -r requirements.txt
```

Create a `.env` file (or copy the example):

```bash
cp .env.example .env
```

Default values in `.env.example`:

```
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=decidio
```

Load the product data into MongoDB:

```bash
python -m scripts.load_db
```

Start the API server:

```bash
python -m uvicorn app.main_mongo:app --host localhost --port 8015 --reload
```

### 3. Set up the frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** in your browser.

### Production build (optional)

```bash
cd frontend
npm run build
```

FastAPI will automatically serve the built frontend from `frontend/dist/` at **http://localhost:8015**.

---

## API Endpoints (Game)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/game/start` | Start a new game session |
| `GET` | `/api/game/{game_id}/onboarding` | Get the 50-pen onboarding pool |
| `POST` | `/api/game/{game_id}/onboarding/submit` | Submit 10 selected pens + rating |
| `POST` | `/api/game/{game_id}/round/start` | Generate the next round's candidates |
| `POST` | `/api/game/{game_id}/round/{round}/pick` | Submit your pick for a round |
| `GET` | `/api/game/{game_id}/status` | Get current game state & scores |
| `GET` | `/api/game/leaderboard` | Global leaderboard |

---

## The ML Model

The recommendation engine is a **prefix-based collaborative filtering** model inspired by research on sequential preference modeling:

- **Feature space**: Each pen is represented by vendor, product type, tags, nib options, and normalized price.
- **User vector**: Built incrementally — updated after each selection with a decay factor so recent picks weigh more.
- **Prefix ratings**: After onboarding, the user's set-level rating adjusts a per-session bias term.
- **Candidate scoring**: Cosine similarity between the user vector and each candidate, plus the bias term.
- **Diversity**: Onboarding pool and round candidates mix top-likelihood picks with decoy/wildcard items.
- **Hidden preference detection**: A latency-score algorithm (`preference_weight − selection_frequency`) identifies features accumulated incidentally rather than intentionally. Products scored against only these hidden dimensions become "Hidden Gem" recommendations.

---

## License

This project was developed as part of CSC 492 (Senior Design) coursework.
