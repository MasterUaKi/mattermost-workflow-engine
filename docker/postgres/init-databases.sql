-- Author: Oleh Riabtsev
-- File: docker/postgres/init-databases.sql
-- Created: 2026-11-23
-- Version: 1.0.0

-- Create a dedicated database for the local Mattermost test server
SELECT 'CREATE DATABASE mattermost_db'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'mattermost_db')\gexec
