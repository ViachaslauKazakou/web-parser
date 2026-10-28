# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Standalone FastAPI web application with PostgreSQL, matching the source workflows; one web process, no workers or queue service.

## Users

Primary user: a local operator researching public forum discussions who needs to collect a user's posts or a full topic, then inspect which replies are most relevant. No application login, user accounts, or role checks are required.

## Product Purpose

ForumScope is a standalone web tool for parsing forum posts/topics and ranking topic replies by relevance. Success means a user can parse or provide a discussion, analyze it, inspect and export ranked results, and revisit saved analyses.

## Positioning

The product joins browser-based forum extraction with a deterministic, explainable relevance ranking pipeline. Ranking works locally without an AI provider; LLM scoring and explanations are optional.

## Operating Context

The app is intended to run locally in a development Docker Compose stack on port 8040, with PostgreSQL for saved analysis history. The web interface is directly accessible without authentication. Inputs include a forum username/user ID, a topic URL, manually entered discussion data, or JSON/CSV files.

## Capabilities and Constraints

- Preserve the parser workflows for user search by username and comments by user ID, pagination, topic parsing, JSON export, and the relevance-analysis workflow.
- Preserve manual JSON/CSV ingestion, deterministic scoring, ranked results, best/low-relevance summaries, saved runs, and optional LLM scoring/explanations.
- Do not carry over internal forum-table integrations, application authentication, user accounts/billing, ARQ/Redis queues, or workers.
- Forum parsing must work without forum credentials by default; optional AI provider credentials are local environment configuration. Never embed credentials from the source project.
- This unauthenticated application is intended for localhost or a trusted private network, not direct public exposure.
- Parser source supports multiple forum markup families, but the default entry domain is searchengines.guru.
- Parser destinations must be configurable and protected by a host allowlist to prevent requests to private/internal network addresses.
- This is a local single-operator development tool, not a public multi-tenant service.

## Product Principles

- Collect and analyze in one direct workflow.
- Keep deterministic ranking available without external AI credentials.
- Make ranking, evidence, and errors inspectable.
- Save completed analysis runs for later review.
- Keep the local development stack limited to the app and its database.
