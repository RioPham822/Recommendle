# Postgres Sync Guide

This guide shows how to copy the existing Postgres database from the VM's Docker container into your local Docker Postgres container.

It assumes both environments use this project's default Postgres setup:

- service name: `postgres`
- database: `decidio`
- username: `decidio`
- password: `decidio_pass`

## What This Does

The workflow is:

1. Create a Postgres dump on the VM from the running Docker container.
2. Copy that dump file from the VM to your local machine.
3. Restore the dump into your local Docker Postgres container.

This will overwrite the matching objects in your local `decidio` database.

## Prerequisites

- The VM already has the project running with Docker Compose.
- Your local machine already has this project checked out.
- Your local Docker Postgres container is running.
- You can SSH into the VM.

Start local Postgres from the repo root if needed:

```bash
docker compose up -d postgres
```

## 1. Create a Dump on the VM

SSH into the VM, `cd` to the project root, then run:

```bash
docker compose exec -T postgres pg_dump -U decidio -d decidio -Fc > decidio_vm.dump
```

Notes:

- `-Fc` creates a Postgres custom-format dump.
- The output file `decidio_vm.dump` is created on the VM host, not inside the container.
- You can choose a different filename if you want.

## 2. Copy the Dump from the VM to Your Local Machine

Run this on your local machine:

```bash
scp your-vm-user@your-vm-host:/path/to/repo/decidio_vm.dump .
```

Example:

```bash
scp ec2-user@203.0.113.10:/home/ec2-user/2026Spring-Team42-Decidio-3/decidio_vm.dump .
```

After this, the dump file should exist in your local current directory.

## 3. Restore into Local Docker Postgres

From your local repo root, restore the dump into the local Docker database:

```bash
docker compose exec -T postgres pg_restore -U decidio -d decidio --clean --if-exists < decidio_vm.dump
```

This drops and recreates objects from the dump in your local `decidio` database.

## 4. Restart the Backend

After restoring, restart the backend so it reconnects cleanly:

```bash
docker compose up -d --build backend
```

## Quick End-to-End Summary

On the VM:

```bash
docker compose exec -T postgres pg_dump -U decidio -d decidio -Fc > decidio_vm.dump
```

On your local machine:

```bash
scp your-vm-user@your-vm-host:/path/to/repo/decidio_vm.dump .
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U decidio -d decidio --clean --if-exists < decidio_vm.dump
docker compose up -d --build backend
```

## Troubleshooting

- `docker compose exec` fails locally:
  Start the container first with `docker compose up -d postgres`.
- `pg_restore` says the database is in use:
  Stop the backend first with `docker compose stop backend`, restore again, then restart backend.
- Authentication fails:
  Confirm your local project is using the default Compose credentials from `docker-compose.yml`.
- Wrong data shows up after restore:
  Make sure the dump was taken from the correct VM project directory and environment.

## Related Docs

- `docs/NGINX_SETUP.md` includes the original backup and restore snippets.
- `docs/DEVELOPMENT.md` covers the standard local Docker workflow.
