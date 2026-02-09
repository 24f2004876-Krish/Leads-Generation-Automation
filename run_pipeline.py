"""
Lead Generation Pipeline — Robust Runner
=========================================
Single entry point for: Scrape Google Maps -> Enrich with Perplexity -> Export to Excel

Features:
  - Checkpoint/resume: each stage saves progress to .tmp/ so a crash at
    stage 2 doesn't lose stage 1 results.
  - Interrupt-safe: KeyboardInterrupt during any stage still exports
    whatever data has been collected so far.
  - Parameterized: fully driven by CLI flags, never hardcoded.
  - Windows-safe: UTF-8 encoding, no emoji, handles PermissionError.

Usage:
    python run_pipeline.py --query Malls --location "Delhi, India" --max-results 5
    python run_pipeline.py --query Restaurants Cafes --location "Mumbai, India" --max-results 10
    python run_pipeline.py --resume                 # resume from last checkpoint
    python run_pipeline.py --query Malls --location "Delhi, India" --skip-enrich
"""

from __future__ import annotations

import json
import sys
import os
import logging

# ── Windows encoding safety ──────────────────────────────────────────────────
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

# Suppress noisy Apify client logs
logging.getLogger("apify_client").setLevel(logging.WARNING)

from tools.utils import (
    PROJECT_ROOT, TMP_DIR,
    CHECKPOINT_SCRAPED, CHECKPOINT_ENRICHED,
    save_checkpoint, load_checkpoint, clear_checkpoints,
)
from tools.google_maps_scraper import scrape_google_maps
from tools.enrich_with_perplexity import enrich_leads
from tools.export_to_excel import export_leads


def run_pipeline(
    search_queries: list[str],
    location: str,
    max_results: int = 5,
    output_path: str = "output/leads.xlsx",
    skip_enrich: bool = False,
    resume: bool = False,
):
    """Run the full lead generation pipeline with checkpoint/resume support."""

    print("=" * 60)
    print("  LEAD GENERATION PIPELINE")
    print("=" * 60)
    print(f"  Search:       {search_queries}")
    print(f"  Location:     {location}")
    print(f"  Max results:  {max_results}")
    print(f"  Output:       {output_path}")
    print(f"  Skip enrich:  {skip_enrich}")
    print(f"  Resume:       {resume}")
    print("=" * 60)

    leads = None

    # ── STEP 1: Scrape ───────────────────────────────────────────────────
    if resume:
        leads, meta = load_checkpoint(CHECKPOINT_ENRICHED)
        if leads:
            print(f"\n[STEP 1/3] Resuming from enriched checkpoint ({len(leads)} leads)")
        else:
            leads, meta = load_checkpoint(CHECKPOINT_SCRAPED)
            if leads:
                print(f"\n[STEP 1/3] Resuming from scraped checkpoint ({len(leads)} leads)")

    if leads is None:
        print("\n[STEP 1/3] Scraping Google Maps...")
        try:
            leads = scrape_google_maps(
                search_queries=search_queries,
                location=location,
                max_results=max_results,
            )
        except KeyboardInterrupt:
            print("\n[PIPELINE] Scraping interrupted. Nothing to export.")
            return
        except Exception as e:
            print(f"\n[PIPELINE] Scraping failed: {e}")
            return

        if not leads:
            print("[PIPELINE] No leads found. Check your search query and location.")
            return

        print(f"[STEP 1/3] OK: {len(leads)} leads scraped")
        save_checkpoint(CHECKPOINT_SCRAPED, leads, {
            "queries": search_queries, "location": location,
        })
        print(f"[STEP 1/3] Checkpoint saved: {CHECKPOINT_SCRAPED.name}")

    # ── STEP 2: Enrich ───────────────────────────────────────────────────
    if skip_enrich:
        print("\n[STEP 2/3] Skipped (--skip-enrich flag)")
        for lead in leads:
            lead.setdefault("business_info", "")
    else:
        # Check if enrichment checkpoint already exists (for resume)
        # Only re-load if we didn't already get leads from the enriched checkpoint
        if resume and CHECKPOINT_ENRICHED.exists() and leads is not None:
            # We already loaded from enriched checkpoint in STEP 1 — skip re-load
            enriched_already = any(l.get("business_info") for l in leads)
            if enriched_already:
                print(f"\n[STEP 2/3] Using enriched checkpoint ({len(leads)} leads)")
            else:
                print("\n[STEP 2/3] Enriching leads with Perplexity...")
                try:
                    leads = enrich_leads(leads)
                except KeyboardInterrupt:
                    print("\n[PIPELINE] Enrichment interrupted. Exporting partial results...")
                    for lead in leads:
                        lead.setdefault("business_info", "")
                except Exception as e:
                    print(f"\n[PIPELINE] Enrichment error: {e}. Exporting with fallbacks...")
                    for lead in leads:
                        lead.setdefault("business_info", "")
        else:
            print("\n[STEP 2/3] Enriching leads with Perplexity...")
            try:
                leads = enrich_leads(leads)
            except KeyboardInterrupt:
                print("\n[PIPELINE] Enrichment interrupted. Exporting partial results...")
                for lead in leads:
                    lead.setdefault("business_info", "")
            except Exception as e:
                print(f"\n[PIPELINE] Enrichment error: {e}. Exporting with fallbacks...")
                for lead in leads:
                    lead.setdefault("business_info", "")

        save_checkpoint(CHECKPOINT_ENRICHED, leads)
        print(f"[STEP 2/3] Checkpoint saved: {CHECKPOINT_ENRICHED.name}")

    # ── STEP 3: Export ───────────────────────────────────────────────────
    print("\n[STEP 3/3] Exporting to Excel...")
    try:
        out_path = export_leads(leads, output_path=output_path)
    except PermissionError as e:
        print(f"\n[PIPELINE] {e}")
        return
    except Exception as e:
        print(f"\n[PIPELINE] Export failed: {e}")
        return

    # Successful run — clear checkpoints
    clear_checkpoints()

    # Print summary
    print("\n" + "=" * 60)
    print("  COMPLETE")
    print("=" * 60)
    for i, lead in enumerate(leads, 1):
        name = lead.get("name", "N/A")
        cat = lead.get("category", "")
        info = lead.get("business_info") or ""
        info_display = (info[:50] + "...") if len(info) > 50 else info
        print(f"  {i}. {name} ({cat}) -- {info_display}")
    print("=" * 60)
    print(f"  Output: {out_path}")
    print("=" * 60)


# ── CLI ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Google Maps Lead Generation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python run_pipeline.py --query Malls --location "Delhi, India" --max-results 5\n'
            '  python run_pipeline.py --query Restaurants Cafes --location "Mumbai" --max-results 10\n'
            "  python run_pipeline.py --resume\n"
        ),
    )
    parser.add_argument("--query", nargs="+", default=["Restaurants"],
                        help="Search queries (e.g., --query Malls Shops)")
    parser.add_argument("--location", default="Delhi, India",
                        help='Location (e.g., --location "Mumbai, India")')
    parser.add_argument("--max-results", type=int, default=5, dest="max_results",
                        help="Max results per query (default: 5)")
    parser.add_argument("--output", default="output/leads.xlsx",
                        help="Output Excel path (default: output/leads.xlsx)")
    parser.add_argument("--skip-enrich", action="store_true",
                        help="Skip Perplexity enrichment step")
    parser.add_argument("--resume", action="store_true",
                        help="Resume from last checkpoint (if available)")

    args = parser.parse_args()

    run_pipeline(
        search_queries=args.query,
        location=args.location,
        max_results=args.max_results,
        output_path=args.output,
        skip_enrich=args.skip_enrich,
        resume=args.resume,
    )
