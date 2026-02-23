# Postgres Atlas Integration Guide

## Overview
Your Decidio application is now configured to work with Postgres Atlas (Postgres's cloud service). This guide will help you set up and connect to Postgres Atlas.

## Step 1: Create a Postgres Atlas Account

1. Go to [Postgres Atlas](https://www.Postgres.com/cloud/atlas)
2. Click "Try Free" or sign in if you already have an account
3. Create a free tier cluster (M0)

## Step 2: Create a Database User

1. In the Postgres Atlas dashboard, navigate to **Database Access**
2. Click **Add New Database User**
3. Choose **Password** as the authentication method
4. Set a username and password
5. Set the user privilege level to **Atlas admin** (for development)
6. Click **Add User**

## Step 3: Get Your Connection String

1. Go to **Database** in the left sidebar
2. Click **Connect** on your cluster
3. Choose **Drivers** as the connection method
4. Select **Driver: Python**
5. Copy the connection string provided

The connection string will look like:
```
Postgres+srv://<username>:<password>@<cluster-url>/myFirstDatabase?retryWrites=true&w=majority
```

## Step 4: Update Your .env File

Replace the `Postgres_URL` in your `.env` file with your Atlas connection string:

```env
Postgres_URL=Postgres+srv://username:password@cluster0.xxxxx.Postgres.net/decidio?retryWrites=true&w=majority
```

**Important:** 
- Replace `<username>` with your database username
- Replace `<password>` with your database password
- Replace `<cluster-url>` with your actual cluster URL
- Keep `decidio` as the database name (or change if preferred)
- Make sure there are no special characters in the URL, or URL-encode them

## Step 5: Whitelist IP Address

1. In Postgres Atlas, go to **Network Access**
2. Click **Add IP Address**
3. Choose one of:
   - Add your current IP
   - Add 0.0.0.0/0 (allows all IPs - for development only!)
4. Confirm

## Step 6: Test the Connection

Run the backend to verify the connection:

```bash
cd backend
python -m uvicorn app.main:app --reload
```

You should see in the logs:
```
Postgres connection verified successfully
```

## Step 7: Deploy to Cloud

When deploying to a cloud service (Azure, AWS, Heroku, etc.), make sure to:
1. Set the `Postgres_URL` environment variable in your deployment service
2. Whitelist the IP address of your cloud deployment in Postgres Atlas Network Access
3. For AWS, Google Cloud, or Azure: whitelist their IP ranges or use VPC peering

## Common Issues

### Connection Timeout
- Check if your IP is whitelisted in Postgres Atlas
- Verify your connection string is correct
- Make sure the password doesn't contain special characters that aren't URL-encoded

### Authentication Failed
- Verify username and password in your connection string
- Ensure the database user has the correct privileges
- Check that your user exists in the correct Postgres Atlas project

### Special Characters in Password
If your password contains special characters, URL-encode them:
- `@` becomes `%40`
- `!` becomes `%21`
- `:` becomes `%3A`
- etc.

## Running Locally

If you want to run Postgres locally instead, update `.env`:
```env
Postgres_URL=Postgres://localhost:27017
```

Make sure Postgres is running:
```bash
Postgresd
```

## Checking Database Contents

Use Postgres Compass or the Atlas UI to browse your data:
1. In Postgres Atlas, click **Connect** â†’ **Postgres Compass**
2. Copy the connection string and open it in Postgres Compass
3. You can now view and manage your databases

## Environment Variables Summary

- `Postgres_URL`: Connection string to Postgres Atlas
- `Postgres_DB_NAME`: Database name (default: decidio)
- `Postgres_MAX_POOL_SIZE`: Maximum connection pool size (default: 10)
- `Postgres_MIN_POOL_SIZE`: Minimum connection pool size (default: 1)
- `TMDB_API_KEY`: API key for movie data (optional)

For more info, see [Postgres Atlas Documentation](https://docs.atlas.Postgres.com/)

