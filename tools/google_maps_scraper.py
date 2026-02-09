"""
WAT Framework — Google Maps Scraper
Fetches business leads from Google Maps using the Apify
"compass/crawler-google-places" actor.

Usage (called by the agent):
    from tools.google_maps_scraper import scrape_google_maps
    leads = scrape_google_maps(
        search_queries=["restaurants"],
        location="New York, USA",
        max_results=50,
    )
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from pathlib import Path

from apify_client import ApifyClient

from tools.utils import TMP_DIR, get_env

# ── Config ──────────────────────────────────────────────────────────────────
ACTOR_ID = "compass/crawler-google-places"
TERMINAL_STATES = frozenset({"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"})

# Suppress verbose Apify client logs globally
logging.getLogger("apify_client").setLevel(logging.WARNING)


def scrape_google_maps(
    search_queries: list[str],
    location: str,
    max_results: int = 10,
    language: str = "en",
    skip_closed: bool = True,
    scrape_contacts: bool = True,
) -> list[dict]:
    """
    Run the Apify Google Maps actor and return cleaned leads.

    Args:
        search_queries:  List of search terms, e.g. ["plumber", "electrician"].
        location:        Free-text location, e.g. "Chicago, USA".
        max_results:     Max places to scrape per search term.
        language:        Results language code (default "en").
        skip_closed:     Skip permanently/temporarily closed places.
        scrape_contacts: Enable email/social enrichment on Apify side.

    Returns:
        List of lead dicts with keys:
            name, category, location, city, state, phone, website, email
    """
    # Validate inputs
    if max_results < 1:
        raise ValueError(f"max_results must be >= 1, got {max_results}")
    if not search_queries:
        raise ValueError("search_queries must not be empty")
    if not location or not location.strip():
        raise ValueError("location must not be empty")

    token = get_env("APIFY_API_TOKEN")
    client = ApifyClient(token)

    run_input = {
        "searchStringsArray": search_queries,
        "locationQuery": location,
        "maxCrawledPlacesPerSearch": max_results,
        "language": language,
        "skipClosedPlaces": skip_closed,
        "scrapeContacts": scrape_contacts,
        "scrapePlaceDetailPage": True,
        "maxReviews": 0,
        "maxImages": 0,
    }

    # Auto-scale timeout: at least 120s, plus 30s per requested result, capped at 600s
    max_wait = min(600, max(120, max_results * 30))
    poll_interval = 10

    print(f"[scraper] Starting Apify actor: {search_queries} in {location}")
    print(f"[scraper] Max results per query: {max_results}")
    print(f"[scraper] Timeout: {max_wait}s ({max_wait // 60}m {max_wait % 60}s)")

    actor_client = client.actor(ACTOR_ID)
    run_info = actor_client.start(run_input=run_input)
    run_id = run_info.get("id")
    if not run_id:
        raise RuntimeError(f"Apify actor.start() returned unexpected response: {run_info}")
    print(f"[scraper] Actor run started: {run_id}")

    # ── Poll with interrupt safety ───────────────────────────────────────
    status = None
    start_time = time.monotonic()

    # Fatal HTTP status codes that should not be retried
    _FATAL_STATUS_CODES = {401, 403, 404}

    try:
        while (time.monotonic() - start_time) < max_wait:
            time.sleep(poll_interval)
            elapsed = int(time.monotonic() - start_time)
            try:
                run = client.run(run_id).get()
                status = run.get("status")
            except Exception as api_err:
                # Distinguish fatal errors from transient ones
                err_str = str(api_err).lower()
                if any(code in err_str for code in ("401", "403", "not found")):
                    raise RuntimeError(
                        f"Fatal Apify API error (non-retryable): {api_err}"
                    ) from api_err
                print(f"[scraper] API poll error ({api_err}), retrying...", flush=True)
                continue
            print(f"[scraper] {elapsed}s / {max_wait}s -- status: {status}", flush=True)
            if status in TERMINAL_STATES:
                break
    except KeyboardInterrupt:
        print(f"\n[scraper] Interrupted! Aborting Apify run {run_id}...")
        try:
            client.run(run_id).abort()
            print("[scraper] Apify run aborted (no further credits consumed).")
        except Exception:
            print(f"[scraper] Could not abort run. Check manually: "
                  f"https://console.apify.com/actors/runs/{run_id}")
        raise

    if status != "SUCCEEDED":
        raise RuntimeError(
            f"Apify actor run did not succeed (status: {status}, "
            f"elapsed: {elapsed}s). "
            f"Check https://console.apify.com/actors/runs/{run_id}"
        )

    # ── Fetch results ────────────────────────────────────────────────────
    final_run = client.run(run_id).get()
    dataset_id = final_run.get("defaultDatasetId")
    if not dataset_id:
        raise RuntimeError(
            f"Apify run completed but returned no dataset ID. "
            f"Response: {final_run}"
        )
    raw_items = client.dataset(dataset_id).list_items().items
    print(f"[scraper] Received {len(raw_items)} raw results")

    # Save raw JSON for caching / debugging
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = TMP_DIR / f"gmaps_raw_{timestamp}.json"
    raw_path.write_text(json.dumps(raw_items, indent=2, default=str), encoding="utf-8")
    print(f"[scraper] Raw data saved: {raw_path}")

    leads = _extract_leads(raw_items)
    print(f"[scraper] Cleaned leads: {len(leads)}")
    return leads


def _extract_leads(raw_items: list[dict]) -> list[dict]:
    """Pull the 8 required fields from each raw Apify result."""
    leads = []
    for item in raw_items:
        # Try to find email from the contacts enrichment
        email = _extract_email(item)

        lead = {
            "name": item.get("title", ""),
            "category": item.get("categoryName", ""),
            "location": item.get("address", ""),
            "city": item.get("city", ""),
            "state": item.get("state", ""),
            "phone": item.get("phone", ""),
            "website": item.get("website", ""),
            "email": email,
        }

        # Replace None with empty string for any field
        lead = {k: (v if v is not None else "") for k, v in lead.items()}
        leads.append(lead)

    return leads


def _extract_email(item: dict) -> str:
    """
    Extract the best email from various Apify enrichment fields.
    The actor may put emails in different locations depending on
    enrichment options enabled.
    """
    # Direct email field (from business leads enrichment)
    if item.get("email"):
        return item["email"]

    # From contacts enrichment — emails list
    emails = item.get("emails")
    if emails and isinstance(emails, list) and len(emails) > 0:
        return emails[0]

    # From contact info nested object
    contact_info = item.get("contactInfo") or {}
    if contact_info.get("email"):
        return contact_info["email"]

    return ""


# ── CLI entry point for testing ──────────────────────────────────────────
if __name__ == "__main__":
    import sys

    query = sys.argv[1] if len(sys.argv) > 1 else "restaurant"
    loc = sys.argv[2] if len(sys.argv) > 2 else "New York, USA"
    max_r = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    results = scrape_google_maps(
        search_queries=[query],
        location=loc,
        max_results=max_r,
    )

    for r in results:
        print(json.dumps(r, indent=2))
