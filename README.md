# 📊 Lead Generation Automation

Automated lead generation pipeline that scrapes business data from Google Maps, enriches each lead with AI-powered summaries, and exports everything to a clean Excel spreadsheet — all from a sleek web UI or the command line.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-Web_UI-FF4B4B?logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## ✨ Features

- **Google Maps Scraping** — Pulls business leads (name, category, address, phone, website, email) using the Apify platform
- **AI Enrichment** — Generates concise 2–3 sentence business summaries via Perplexity Sonar AI with real-time web search
- **Excel Export** — Produces styled `.xlsx` files with formatted headers, auto-fit columns, and de-duplication
- **Web UI** — Beautiful Streamlit interface with real-time logs, progress tracking, stats dashboard, and one-click download
- **CLI Support** — Fully parameterized command-line runner for scripting and automation
- **Checkpoint/Resume** — Crash-safe pipeline that saves progress after each stage, so interrupted runs can resume without losing data
- **Cost-Efficient** — ~$1.10 per 100 leads (Apify scraping + Perplexity enrichment)

---

## 🏗️ Architecture

This project follows the **WAT Framework** (Workflows, Agents, Tools):

```
┌─────────────────────────────────────────────────┐
│  Streamlit Web UI (app.py)                      │
│  or CLI Runner (run_pipeline.py)                │
└──────────────┬──────────────────────────────────┘
               │
     ┌─────────▼─────────┐
     │  Pipeline Engine   │  Orchestrates 3 stages
     └─────────┬─────────┘
               │
  ┌────────────┼────────────────┐
  ▼            ▼                ▼
┌──────┐  ┌──────────┐  ┌──────────┐
│Scrape│  │ Enrich   │  │ Export   │
│GMaps │→ │Perplexity│→ │ Excel   │
└──────┘  └──────────┘  └──────────┘
```

| Stage | Tool | What it does |
|-------|------|-------------|
| 1. Scrape | `tools/google_maps_scraper.py` | Runs the Apify Google Maps actor to fetch leads with contact info |
| 2. Enrich | `tools/enrich_with_perplexity.py` | Calls Perplexity Sonar API for AI-generated business summaries |
| 3. Export | `tools/export_to_excel.py` | Writes styled, de-duplicated Excel spreadsheet |

---

## 📋 Prerequisites

- **Python 3.10+**
- **Apify Account** — [Sign up here](https://console.apify.com/) (free tier available)
- **Perplexity API Key** — [Get one here](https://www.perplexity.ai/settings/api) (optional — can skip enrichment)

---

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/your-username/lead-generation-automation.git
cd lead-generation-automation
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

Create a `.env` file in the project root:

```env
APIFY_API_TOKEN=your_apify_token_here
PERPLEXITY_API_KEY=your_perplexity_key_here
```

| Variable | Required | Where to get it |
|----------|----------|----------------|
| `APIFY_API_TOKEN` | ✅ Yes | [Apify Console → Settings → Integrations](https://console.apify.com/settings/integrations) |
| `PERPLEXITY_API_KEY` | ❌ Optional | [Perplexity Settings → API](https://www.perplexity.ai/settings/api) |

> **Note:** If you skip the Perplexity key, you can still run the pipeline with the `--skip-enrich` flag (CLI) or the "Skip AI Enrichment" checkbox (Web UI).

### 4. Run the application

#### Option A: Web UI (Recommended)

```bash
streamlit run app.py
```

This opens a browser with the full web interface where you can:
- Enter search queries and location
- Configure max results and output filename
- Watch real-time logs during execution
- View results with stats (total leads, emails found, etc.)
- Download the Excel file directly

#### Option B: Command Line

```bash
# Basic usage
python run_pipeline.py --query Restaurants --location "Delhi, India" --max-results 5

# Multiple search queries
python run_pipeline.py --query Restaurants Cafes Hotels --location "Mumbai, India" --max-results 10

# Skip AI enrichment (faster, no Perplexity API needed)
python run_pipeline.py --query Malls --location "Delhi, India" --skip-enrich

# Resume an interrupted run
python run_pipeline.py --resume

# Custom output file
python run_pipeline.py --query Plumbers --location "Chicago, USA" --output output/plumbers_chicago.xlsx
```

---

## 📁 Project Structure

```
lead-generation-automation/
├── app.py                  # Streamlit web UI
├── run_pipeline.py         # CLI pipeline runner
├── requirements.txt        # Python dependencies
├── .env                    # API keys (create this - gitignored)
├── CLAUDE.md               # AI agent instructions (WAT framework)
│
├── tools/                  # Deterministic execution scripts
│   ├── google_maps_scraper.py    # Apify Google Maps scraper
│   ├── enrich_with_perplexity.py # Perplexity AI enrichment
│   ├── export_to_excel.py        # Excel export with styling
│   └── utils.py                  # Shared utilities & checkpoint logic
│
├── workflows/              # Markdown SOPs for AI agents
│   ├── google_maps_leads.md      # Lead generation workflow
│   └── _template.md              # Workflow template
│
├── output/                 # Generated Excel files
│   └── leads.xlsx
│
└── .tmp/                   # Temporary files & checkpoints (auto-created)
```

---

## 📊 Output Format

The generated Excel file contains the following columns:

| Column | Description | Example |
|--------|-------------|---------|
| **Name** | Business name | Joe's Pizza |
| **Category** | Business category | Pizza restaurant |
| **Location** | Full address | 7 Carmine St, New York, NY 10014 |
| **City** | City name | New York |
| **State** | State/region | NY |
| **Phone No.** | Phone number | (212) 366-1182 |
| **Website** | Business website | https://www.joespizzanyc.com |
| **Email** | Contact email | info@joespizzanyc.com |
| **Business Info** | AI-generated summary | Joe's Pizza is an iconic New York-style pizzeria... |

---

## 💰 Cost Estimates

| Component | Cost |
|-----------|------|
| Apify — Place scraping | ~$4 / 1,000 places |
| Apify — Contact enrichment | ~$2 / 1,000 places |
| Perplexity — Business summaries | ~$0.005 / lead |
| **Total for 100 leads** | **~$1.10** |

> **Tip:** Use `--max-results` conservatively. Start with 5–10 to test, then scale up.

---

## ⚙️ Configuration

### Perplexity Rate Limits

The default delay between API calls is 1.2 seconds (~50 requests/min) for Tier-0 accounts. If you have a higher-tier Perplexity plan, you can speed things up:

```env
PERPLEXITY_RATE_LIMIT_DELAY=0.3   # For Tier-1+ accounts
```

### Apify Actor

The scraper uses the `compass/crawler-google-places` actor. The timeout auto-scales based on `max_results`:
- Minimum: 120 seconds
- Formula: `max_results × 30 seconds`
- Maximum: 600 seconds (10 minutes)

---

## 🔧 CLI Reference

```
python run_pipeline.py [OPTIONS]

Options:
  --query QUERY [QUERY ...]   Search queries (default: Restaurants)
  --location LOCATION         Target location (default: "Delhi, India")
  --max-results N             Max results per query (default: 5)
  --output PATH               Output Excel path (default: output/leads.xlsx)
  --skip-enrich               Skip Perplexity AI enrichment step
  --resume                    Resume from last checkpoint
  -h, --help                  Show help message
```

---

## 🛡️ Resilience Features

- **Checkpoint/Resume** — Progress is saved to `.tmp/` after scraping and enrichment. If the pipeline crashes or is interrupted, use `--resume` to pick up where it left off
- **Interrupt Safety** — `Ctrl+C` during any stage gracefully aborts, saves partial data, and exports whatever has been collected
- **Retry Logic** — API calls include exponential backoff for transient failures
- **Fallback Summaries** — If Perplexity fails for a specific lead, a basic summary is generated from the business name and category
- **De-duplication** — Duplicate leads (by Name + Location) are automatically skipped
- **File Lock Handling** — Excel export retries if the output file is open in another application

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is open source and available under the [MIT License](LICENSE).

---

<div align="center">
  <strong>Built with</strong> Apify · Perplexity AI · Streamlit
  <br><br>
  © 2026 Krish Jain. All rights reserved.
</div>
