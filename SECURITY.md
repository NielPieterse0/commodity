# Security

## Scope

This repository contains experimental research code and configuration. It does not authorize live trading; binding execution authority is owned by `config/trading-policy.json`.

## Reporting a vulnerability

Do not publish credentials, tokens, private data, exploitable details, or proof-of-concept secrets in a public issue or pull request. Report security-sensitive findings privately to the repository owner through GitHub's private security-reporting channel when available.

## Secret and local-state boundary

Credentials belong in local environment variables or ignored `.env` files only. Never commit API keys, access tokens, private keys, cookies, provider credentials, broker credentials, licensed raw market data, machine-specific runtime state, caches, quarantine payloads, or local provider installations.

`.env.example` may document variable names only; it must not contain usable credentials.

Before publication, repository history and all public refs must pass secret-history review. A clean current tree is not sufficient if a credential existed in Git history.
