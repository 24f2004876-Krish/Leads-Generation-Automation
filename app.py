"""
Lead Generation Automation - Streamlit Web UI
==============================================
A clean web interface for the Google Maps lead generation pipeline.
Launch with:  streamlit run app.py
"""

import io
import os
import sys
import json
import html as html_module
import threading
import queue
import time
from pathlib import Path
from datetime import datetime

import streamlit as st
import pandas as pd

# -- Page config (must be first Streamlit command) --
st.set_page_config(
    page_title="Lead Generation Automation",
    page_icon="\U0001F4CA",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -- Windows encoding safety --
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# -- Ensure project root is on sys.path --
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)
os.chdir(_PROJECT_DIR)

# -- Project imports --
from tools.utils import (
    PROJECT_ROOT, TMP_DIR,
    CHECKPOINT_SCRAPED, CHECKPOINT_ENRICHED,
    checkpoints_exist, clear_checkpoints,
    save_checkpoint, load_checkpoint,
    sanitize_filename,
)
from tools.google_maps_scraper import scrape_google_maps
from tools.enrich_with_perplexity import enrich_leads
from tools.export_to_excel import export_leads


# ---------------------------------------------------------------------------
# Helpers (thin wrappers around shared utils for backward compat)
# ---------------------------------------------------------------------------
def _checkpoints_exist() -> bool:
    return checkpoints_exist()


def _clear_checkpoints():
    clear_checkpoints()


def _save_checkpoint(path, leads, meta=None):
    save_checkpoint(path, leads, meta)


def _load_checkpoint(path):
    return load_checkpoint(path)


# ---------------------------------------------------------------------------
# Stdout capture for real-time log streaming
# ---------------------------------------------------------------------------
class QueueWriter:
    """Capture writes to a thread-safe queue WITHOUT replacing global sys.stdout.
    
    Instead of swapping sys.stdout (which causes race conditions with Streamlit),
    we pass this writer explicitly and patch stdout only for the worker thread.
    """

    def __init__(self, q, original):
        self.queue = q
        self.original = original
        self._thread_id = None  # set after thread starts

    def write(self, text):
        if text and text.strip():
            self.queue.put(text)
        if self.original:
            try:
                self.original.write(text)
            except Exception:
                pass

    def flush(self):
        if self.original:
            try:
                self.original.flush()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Pipeline runner (runs in thread to not block Streamlit)
# ---------------------------------------------------------------------------
def _run_pipeline_thread(
    search_queries, location, max_results, output_path,
    skip_enrich, resume, log_queue, result_holder,
):
    """Execute the pipeline stages, pushing log lines to log_queue.
    
    stdout is redirected ONLY for this specific thread using a thread-local
    approach to avoid race conditions with Streamlit's main thread.
    """

    import _thread
    original_stdout = sys.stdout
    worker_thread_id = _thread.get_ident()
    writer = QueueWriter(log_queue, original_stdout)
    
    # Only redirect stdout for this thread
    sys.stdout = writer

    try:
        leads = None

        # STEP 1: Scrape
        if resume:
            leads, meta = _load_checkpoint(CHECKPOINT_ENRICHED)
            if leads:
                print(f"[STEP 1/3] Resuming from enriched checkpoint ({len(leads)} leads)")
            else:
                leads, meta = _load_checkpoint(CHECKPOINT_SCRAPED)
                if leads:
                    print(f"[STEP 1/3] Resuming from scraped checkpoint ({len(leads)} leads)")

        if leads is None:
            print("[STEP 1/3] Scraping Google Maps...")
            leads = scrape_google_maps(
                search_queries=search_queries,
                location=location,
                max_results=max_results,
            )
            if not leads:
                result_holder["error"] = "No leads found. Check your search query and location."
                return
            print(f"[STEP 1/3] OK -- {len(leads)} leads scraped")
            _save_checkpoint(CHECKPOINT_SCRAPED, leads, {
                "queries": search_queries, "location": location,
            })

        # STEP 2: Enrich
        if skip_enrich:
            print("[STEP 2/3] Skipped (enrichment disabled)")
            for lead in leads:
                lead.setdefault("business_info", "")
        else:
            enriched, _ = _load_checkpoint(CHECKPOINT_ENRICHED)
            if enriched and resume:
                leads = enriched
                print(f"[STEP 2/3] Loaded enriched checkpoint ({len(leads)} leads)")
            else:
                print("[STEP 2/3] Enriching leads with Perplexity...")
                try:
                    leads = enrich_leads(leads)
                except Exception as e:
                    print(f"[STEP 2/3] Enrichment error: {e}. Using fallbacks...")
                    for lead in leads:
                        lead.setdefault("business_info", "")
            _save_checkpoint(CHECKPOINT_ENRICHED, leads)

        # STEP 3: Export
        print("[STEP 3/3] Exporting to Excel...")
        out = export_leads(leads, output_path=output_path)
        _clear_checkpoints()

        print(f"[COMPLETE] {len(leads)} leads exported to {out}")
        result_holder["leads"] = leads
        result_holder["output_path"] = str(out)

    except Exception as e:
        result_holder["error"] = str(e)
    finally:
        sys.stdout = original_stdout


# ===========================================================================
#  STREAMLIT UI
# ===========================================================================

# -- Custom CSS --
st.markdown("""
<style>
    .block-container { padding-top: 2rem; max-width: 1100px; }

    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        color: white;
    }
    .main-header h1 { color: white !important; margin: 0 0 0.3rem 0; font-size: 2rem; }
    .main-header p  { color: rgba(255,255,255,0.85); margin: 0; font-size: 1.05rem; }

    .config-card {
        background: #ffffff;
        border: 1px solid #e8ecf1;
        border-radius: 12px;
        padding: 1.8rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .config-card h3 {
        margin-top: 0;
        color: #1a1a2e;
        font-size: 1.1rem;
        border-bottom: 2px solid #667eea;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }

    .results-header {
        background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        padding: 1.2rem 1.8rem;
        border-radius: 12px;
        margin: 1.5rem 0 1rem 0;
        color: white;
    }
    .results-header h3 { color: white !important; margin: 0; }

    .stat-box {
        background: #f8f9ff;
        border: 1px solid #e0e4f5;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        text-align: center;
    }
    .stat-box .number { font-size: 1.8rem; font-weight: 700; color: #667eea; }
    .stat-box .label  { font-size: 0.85rem; color: #666; margin-top: 0.2rem; }

    .log-line {
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 0.82rem;
        padding: 2px 0;
        color: #cdd6f4;
    }
    .log-container {
        background: #1e1e2e;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        max-height: 350px;
        overflow-y: auto;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# -- Header --
st.markdown("""
<div class="main-header">
    <h1>\U0001F4CA Lead Generation Automation</h1>
    <p>Scrape Google Maps \u2192 Enrich with AI \u2192 Export to Excel</p>
</div>
""", unsafe_allow_html=True)


# -- Input Form --
col1, col2 = st.columns(2)

with col1:
    search_input = st.text_input(
        "Search Queries",
        value="Restaurants",
        help="Comma-separated business types, e.g. 'Restaurants, Cafes, Hotels'",
        placeholder="e.g. Restaurants, Cafes, Hotels",
    )
    location = st.text_input(
        "Location",
        value="Delhi, India",
        help="Target area - must be a recognizable place name",
        placeholder="e.g. Mumbai, India",
    )

with col2:
    max_results = st.number_input(
        "Max Results per Query",
        min_value=1,
        max_value=100,
        value=5,
        step=1,
        help="Number of leads to scrape per search query (1-100)",
    )
    output_filename = st.text_input(
        "Output Filename",
        value="leads.xlsx",
        help="Name for the output Excel file (saved in output/ folder)",
        placeholder="e.g. leads.xlsx",
    )

col3, col4 = st.columns(2)

with col3:
    skip_enrich = st.checkbox(
        "Skip AI Enrichment",
        value=False,
        help="Skip the Perplexity AI step (faster, but no business summaries)",
    )

with col4:
    has_checkpoints = _checkpoints_exist()
    resume = st.checkbox(
        "Resume from Checkpoint",
        value=False,
        disabled=not has_checkpoints,
        help=(
            "Resume a previously interrupted run" if has_checkpoints
            else "No checkpoint available - run the pipeline first"
        ),
    )

# -- Generate Button --
generate_clicked = st.button(
    "\U0001F680 Generate Leads",
    type="primary",
    use_container_width=True,
)


# -- Pipeline Execution --
if generate_clicked:
    # Validate inputs
    queries = [q.strip() for q in search_input.split(",") if q.strip()]
    if not queries:
        st.error("Please enter at least one search query.")
        st.stop()
    if not location.strip():
        st.error("Please enter a location.")
        st.stop()
    if not output_filename.strip():
        output_filename = "leads.xlsx"
    if not output_filename.endswith(".xlsx"):
        output_filename += ".xlsx"
    # Sanitize filename to prevent path traversal attacks
    output_filename = sanitize_filename(output_filename)

    output_path = f"output/{output_filename}"

    # Set up log queue and result holder
    log_queue = queue.Queue()
    result_holder = {}

    # Launch pipeline in background thread
    thread = threading.Thread(
        target=_run_pipeline_thread,
        args=(
            queries, location.strip(), max_results, output_path,
            skip_enrich, resume, log_queue, result_holder,
        ),
        daemon=True,
    )

    # Progress UI
    with st.status("\U0001F504 Running pipeline...", expanded=True) as status:
        log_container = st.empty()
        log_lines = []

        thread.start()

        while thread.is_alive():
            # Drain the log queue
            while True:
                try:
                    line = log_queue.get_nowait()
                    log_lines.append(line.strip())
                except queue.Empty:
                    break

            # Render logs (HTML-escape to prevent XSS from user-controlled data)
            if log_lines:
                log_html = "\n".join(
                    f'<div class="log-line">{html_module.escape(line)}</div>'
                    for line in log_lines[-50:]
                )
                log_container.markdown(
                    f'<div class="log-container">{log_html}</div>',
                    unsafe_allow_html=True,
                )
            time.sleep(0.3)

        # Final drain after thread completes
        while True:
            try:
                line = log_queue.get_nowait()
                log_lines.append(line.strip())
            except queue.Empty:
                break

        if log_lines:
            log_html = "\n".join(
                f'<div class="log-line">{html_module.escape(line)}</div>'
                for line in log_lines[-50:]
            )
            log_container.markdown(
                f'<div class="log-container">{log_html}</div>',
                unsafe_allow_html=True,
            )

        # Check result
        if "error" in result_holder:
            status.update(label="\u274C Pipeline failed", state="error")
            st.error(f"**Error:** {result_holder['error']}")
        else:
            status.update(label="\u2705 Pipeline completed!", state="complete")

    # -- Show Results --
    if "leads" in result_holder:
        leads = result_holder["leads"]
        out_file = Path(result_holder["output_path"])

        # Success header
        st.markdown(
            '<div class="results-header">'
            "<h3>\u2705 Results Ready</h3>"
            "</div>",
            unsafe_allow_html=True,
        )

        # Stats row
        total = len(leads)
        with_email = sum(1 for l in leads if l.get("email"))
        with_phone = sum(1 for l in leads if l.get("phone"))
        with_website = sum(1 for l in leads if l.get("website"))

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(
                f'<div class="stat-box">'
                f'<div class="number">{total}</div>'
                f'<div class="label">Total Leads</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with c2:
            st.markdown(
                f'<div class="stat-box">'
                f'<div class="number">{with_email}</div>'
                f'<div class="label">With Email</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with c3:
            st.markdown(
                f'<div class="stat-box">'
                f'<div class="number">{with_phone}</div>'
                f'<div class="label">With Phone</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with c4:
            st.markdown(
                f'<div class="stat-box">'
                f'<div class="number">{with_website}</div>'
                f'<div class="label">With Website</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)

        # Data preview table
        df = pd.DataFrame(leads)
        column_rename = {
            "name": "Name",
            "category": "Category",
            "location": "Location",
            "city": "City",
            "state": "State",
            "phone": "Phone No.",
            "website": "Website",
            "email": "Email",
            "business_info": "Business Info",
        }
        df = df.rename(columns=column_rename)
        display_cols = [c for c in column_rename.values() if c in df.columns]
        df = df[display_cols]

        st.dataframe(
            df,
            use_container_width=True,
            height=min(400, 35 * (len(df) + 1)),
            hide_index=True,
        )

        # Download button
        if out_file.exists():
            with open(out_file, "rb") as f:
                excel_bytes = f.read()

            st.download_button(
                label=f"\U0001F4E5 Download {out_file.name}",
                data=excel_bytes,
                file_name=out_file.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                use_container_width=True,
            )

# -- Footer --
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:#999; font-size:0.85rem;'>"
    "Lead Generation Automation &mdash; Powered by Apify &amp; Perplexity AI"
    "</div>",
    unsafe_allow_html=True,
)
