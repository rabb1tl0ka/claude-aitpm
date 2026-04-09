# Idea: Team Query Response Cache

## Context
When the AI TPM is exposed to the team via Slack, multiple people may ask the same or similar questions. Caching responses avoids redundant agent runs and speeds up repeat queries.

## How it would work
- Cache key: normalized prompt (lowercased, stripped of @mentions and punctuation)
- Cache value: the response text + metadata (tickets referenced, timestamp)
- Storage: files in `state/query_cache/` — one JSON file per cached query

## Invalidation rules
- **Time-based:** expire after 24h regardless
- **Event-based:** if any ticket referenced in the cached response has changed state since the response was generated, invalidate the cache entry
- **On invalidation:** delete (do not proactively refresh — let the next request trigger a fresh fetch)

## Scoping consideration
- **Ticket-specific queries** ("what's the status of CLOUD-XXXX?"): easy to invalidate precisely — cache entry stores the ticket key, monitor run updates trigger a check
- **Broad queries** ("what's blocking the team?", "what's left in this sprint?"): hard to invalidate precisely — just use the 24h TTL

## Not needed day 1
Ship the team feature without cache first. Add this once query volume justifies it.
