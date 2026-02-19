# MongoDB Atlas Integration Guide

## Overview
Your Decidio application is now configured to work with MongoDB Atlas (MongoDB's cloud service). This guide will help you set up and connect to MongoDB Atlas.

## Step 1: Create a MongoDB Atlas Account

1. Go to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas)
2. Click "Try Free" or sign in if you already have an account
3. Create a free tier cluster (M0)

## Step 2: Create a Database User

1. In the MongoDB Atlas dashboard, navigate to **Database Access**
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
mongodb+srv://<username>:<password>@<cluster-url>/myFirstDatabase?retryWrites=true&w=majority
```

## Step 4: Update Your .env File

Replace the `MONGODB_URL` in your `.env` file with your Atlas connection string:

```env
MONGODB_URL=mongodb+srv://username:password@cluster0.xxxxx.mongodb.net/decidio?retryWrites=true&w=majority
```

**Important:** 
- Replace `<username>` with your database username
- Replace `<password>` with your database password
- Replace `<cluster-url>` with your actual cluster URL
- Keep `decidio` as the database name (or change if preferred)
- Make sure there are no special characters in the URL, or URL-encode them

## Step 5: Whitelist IP Address

1. In MongoDB Atlas, go to **Network Access**
2. Click **Add IP Address**
3. Choose one of:
   - Add your current IP
   - Add 0.0.0.0/0 (allows all IPs - for development only!)
4. Confirm

## Step 6: Test the Connection

Run the backend to verify the connection:

```bash
cd backend
python -m uvicorn app.main_mongo:app --reload
```

You should see in the logs:
```
MongoDB connection verified successfully
```

## Step 7: Deploy to Cloud

When deploying to a cloud service (Azure, AWS, Heroku, etc.), make sure to:
1. Set the `MONGODB_URL` environment variable in your deployment service
2. Whitelist the IP address of your cloud deployment in MongoDB Atlas Network Access
3. For AWS, Google Cloud, or Azure: whitelist their IP ranges or use VPC peering

## Common Issues

### Connection Timeout
- Check if your IP is whitelisted in MongoDB Atlas
- Verify your connection string is correct
- Make sure the password doesn't contain special characters that aren't URL-encoded

### Authentication Failed
- Verify username and password in your connection string
- Ensure the database user has the correct privileges
- Check that your user exists in the correct MongoDB Atlas project

### Special Characters in Password
If your password contains special characters, URL-encode them:
- `@` becomes `%40`
- `!` becomes `%21`
- `:` becomes `%3A`
- etc.

## Running Locally

If you want to run MongoDB locally instead, update `.env`:
```env
MONGODB_URL=mongodb://localhost:27017
```

Make sure MongoDB is running:
```bash
mongod
```

## Checking Database Contents

Use MongoDB Compass or the Atlas UI to browse your data:
1. In MongoDB Atlas, click **Connect** → **MongoDB Compass**
2. Copy the connection string and open it in MongoDB Compass
3. You can now view and manage your databases

## Environment Variables Summary

- `MONGODB_URL`: Connection string to MongoDB Atlas
- `MONGODB_DB_NAME`: Database name (default: decidio)
- `MONGODB_MAX_POOL_SIZE`: Maximum connection pool size (default: 10)
- `MONGODB_MIN_POOL_SIZE`: Minimum connection pool size (default: 1)
- `TMDB_API_KEY`: API key for movie data (optional)

For more info, see [MongoDB Atlas Documentation](https://docs.atlas.mongodb.com/)
