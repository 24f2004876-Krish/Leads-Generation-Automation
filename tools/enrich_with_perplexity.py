"""
WAT Framework — Lead Enrichment via Perplexity Sonar
Generates a concise business summary for each lead using Perplexity's
real-time web search.  If the lead has a website, Perplexity researches
it.  Otherwise, it infers info from the business name + category.

Usage (called by the agent):
    from tools.enrich_with_perplexity import enrich_leads
    enriched = enrich_leads(leads)
"""

from __future__ import annotations

import os
import time
import requests

from tools.utils import get_env

# ── Config ──────────────────────────────────────────────────────────────────
PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
MODEL = "sonar"                       # cheapest model (~$0.005/query)
# Rate-limit delay: configurable via env for users on higher Perplexity tiers.
# Default 1.2s = ~50 RPM (Tier-0 limit). Set PERPLEXITY_RATE_LIMIT_DELAY=0.3 for Tier-1+.
DELAY_BETWEEN_CALLS = float(os.getenv("PERPLEXITY_RATE_LIMIT_DELAY", "1.2"))
MAX_RETRIES = 3                       # retries per API call
BASE_BACKOFF = 2.0                    # exponential backoff base (seconds)
API_TIMEOUT = 45                      # seconds per request
COST_PER_LEAD = 0.005                 # approximate cost per Sonar query


def enrich_leads(leads: list[dict]) -> list[dict]:
    """
    Add a 'business_info' key to each lead dict with a concise summary.

    Args:
        leads: List of lead dicts (must have at least 'name', 'category',
               'city', 'state', 'website' keys).

    Returns:
        The same list with an added 'business_info' field on each lead.
    """
    api_key = get_env("PERPLEXITY_API_KEY")

    if not leads:
        print("[enrich] No leads to enrich.")
        return leads
    if not isinstance(leads, list):
        raise TypeError(f"leads must be a list, got {type(leads).__name__}")

    total = len(leads)
    unenriched = sum(1 for l in leads if not l.get("business_info"))
    est_cost = unenriched * COST_PER_LEAD
    if unenriched > 20:
        print(f"[enrich] Cost estimate: ~${est_cost:.2f} for {unenriched} leads "
              f"(${COST_PER_LEAD}/lead using {MODEL})")

    success = 0
    failed = 0

    for idx, lead in enumerate(leads, 1):
        # Skip already-enriched leads (checkpoint resume support)
        if lead.get("business_info"):
            success += 1
            continue

        name = lead.get("name", "")
        category = lead.get("category", "")
        city = lead.get("city", "")
        state = lead.get("state", "")
        website = lead.get("website", "")

        print(f"[enrich] ({idx}/{total}) Enriching: {name}", flush=True)

        prompt = _build_prompt(name, category, city, state, website)

        try:
            summary = _call_perplexity(api_key, prompt)
            lead["business_info"] = summary.strip()
            success += 1
        except KeyboardInterrupt:
            print(f"\n[enrich] Interrupted at {idx}/{total}. "
                  f"Partial results preserved.")
            # Fill remaining leads with fallback so export still works
            for remaining in leads[idx - 1:]:
                if not remaining.get("business_info"):
                    remaining["business_info"] = _fallback_summary(
                        remaining.get("name", ""), remaining.get("category", ""),
                        remaining.get("city", ""), remaining.get("state", ""),
                    )
            break
        except Exception as e:
            print(f"[enrich] WARN: Failed for '{name}': {e}")
            lead["business_info"] = _fallback_summary(name, category, city, state)
            failed += 1

        # Rate-limit delay (skip after last item)
        if idx < total:
            time.sleep(DELAY_BETWEEN_CALLS)

    print(f"[enrich] Done -- {success} enriched, {failed} fallbacks")
    return leads


# ── Internal helpers ─────────────────────────────────────────────────────────

def _build_prompt(name: str, category: str, city: str, state: str, website: str) -> str:
    """Build the user prompt depending on whether a website exists."""
    location_str = ", ".join(filter(None, [city, state]))

    if website:
        return (
            f"Research the business website {website} for '{name}' "
            f"({category}) located in {location_str}. "
            f"Write a 2-3 sentence concise summary covering: what the business does, "
            f"its key services or products, and any notable highlights. "
            f"Keep it factual and professional."
        )
    else:
        return (
            f"The business '{name}' is listed under the category '{category}' "
            f"in {location_str}. It does not have a website. "
            f"Based on the business name and category, write a 2-3 sentence concise "
            f"summary of what this business likely offers, its typical services, "
            f"and target customers. Keep it factual and professional."
        )


def _call_perplexity(api_key: str, user_prompt: str) -> str:
    """Call Perplexity Sonar API with retry + exponential backoff."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a business research assistant. "
                    "Provide concise, factual summaries about businesses. "
                    "Do not use markdown formatting. Keep responses to 2-3 sentences."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        "num_search_results": 5,
    }

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                PERPLEXITY_URL, headers=headers, json=payload, timeout=API_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()

            # Validate response structure
            choices = data.get("choices")
            if not choices or not isinstance(choices, list):
                raise ValueError(f"Unexpected API response: no 'choices' key")
            content = choices[0].get("message", {}).get("content", "")
            if not content:
                raise ValueError("Empty content in API response")
            return content

        except KeyboardInterrupt:
            raise  # never swallow Ctrl+C
        except requests.exceptions.HTTPError as e:
            # Don't retry on client errors (4xx) — they won't succeed
            if e.response is not None and 400 <= e.response.status_code < 500:
                raise RuntimeError(
                    f"Perplexity API client error (HTTP {e.response.status_code}): "
                    f"{e.response.text[:200]}. Check your API key and account."
                ) from e
            last_err = e
            if attempt < MAX_RETRIES:
                wait = BASE_BACKOFF ** attempt
                print(f"[enrich] Retry {attempt}/{MAX_RETRIES} in {wait:.0f}s: {e}")
                time.sleep(wait)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                wait = BASE_BACKOFF ** attempt
                print(f"[enrich] Retry {attempt}/{MAX_RETRIES} in {wait:.0f}s: {e}")
                time.sleep(wait)

    raise RuntimeError(f"Perplexity API failed after {MAX_RETRIES} attempts: {last_err}")


def _fallback_summary(name: str, category: str, city: str, state: str) -> str:
    """Generate a basic fallback if the API call fails entirely."""
    location_str = ", ".join(filter(None, [city, state]))
    parts = [f"{name} is a {category} business" if category else f"{name} is a local business"]
    if location_str:
        parts[0] += f" located in {location_str}"
    parts[0] += "."
    return " ".join(parts)


# ── CLI entry point for testing ──────────────────────────────────────────────
if __name__ == "__main__":
    sample_leads = [
        {
            "name": "Joe's Pizza",
            "category": "Pizza restaurant",
            "city": "New York",
            "state": "NY",
            "website": "https://www.joespizzanyc.com",
        },
        {
            "name": "Quick Fix Plumbing",
            "category": "Plumber",
            "city": "Chicago",
            "state": "IL",
            "website": "",
        },
    ]

    enriched = enrich_leads(sample_leads)
    for lead in enriched:
        print(f"\n{lead['name']}: {lead['business_info']}")
