# Workflow: Google Maps Lead Generation

## Objective
Extract business leads from Google Maps for a given search query and location, enrich each lead with a concise business summary, and export everything to an Excel file.

## When to Use
When the user needs a list of businesses (leads) for a specific category and location — e.g., "plumbers in Chicago" or "restaurants in New York" — with contact details and a brief description of each business.

## Required Inputs
- **Search Queries**: One or more business types to search for (e.g., `["plumber", "electrician"]`)
- **Location**: Target area as free text (e.g., `"Chicago, USA"`)
- **Max Results**: Maximum number of leads per search query (default: 5)
- **Output File**: Path for the Excel file (default: `output/leads.xlsx`)

## Tools Used
- `tools/google_maps_scraper.py` — Calls the Apify "compass/crawler-google-places" actor to fetch leads from Google Maps with contact enrichment
- `tools/enrich_with_perplexity.py` — Calls Perplexity Sonar API to generate a concise business summary for each lead (uses website if available, otherwise infers from name/category)
- `tools/export_to_excel.py` — Writes/appends the enriched leads to a styled Excel file with de-duplication

## Steps
1. **Scrape Google Maps** — Call `scrape_google_maps(search_queries, location, max_results)`. This runs the Apify actor, saves raw JSON to `.tmp/`, and returns a cleaned list of leads with fields: Name, Category, Location, City, State, Phone No., Website, Email.

2. **Enrich with Perplexity** — Call `enrich_leads(leads)`. For each lead:
   - If it has a **website** → Perplexity researches the site and writes a 2-3 sentence summary.
   - If it has **no website** → Perplexity infers a summary from the business name + category + location.
   - Adds a `business_info` field to each lead dict.

3. **Export to Excel** — Call `export_leads(leads, output_path)`. Creates or appends to an `.xlsx` file with columns: Name, Category, Location, City, State, Phone No., Website, Email, Business Info. Skips any leads already present (de-duplicated by Name + Location).

## Expected Output
An Excel file (`.xlsx`) at the specified output path containing one row per lead with 9 columns. The file has styled headers, frozen top row, and reasonable column widths.

## Cost Estimates
| Component | Cost |
|---|---|
| Apify: Basic place scraping | ~$4 / 1,000 places |
| Apify: Contact enrichment | ~$2 / 1,000 places |
| Perplexity: Business summary | ~$0.005 / lead (sonar model) |
| **Total for 100 leads** | **~$1.10** |

## Edge Cases & Lessons Learned
- **Apify actor ID**: Using `compass/crawler-google-places`. If the user references a different actor ID, update the `ACTOR_ID` constant in `google_maps_scraper.py`.
- **Empty results**: If the actor returns 0 results, check the `locationQuery` — it must be a recognizable place name. Also verify `APIFY_API_TOKEN` is valid.
- **Missing emails**: Not all businesses have emails. The `scrapeContacts` flag helps but won't find emails for every business. The Email column will be left blank when unavailable.
- **Perplexity rate limits**: Tier-0 allows 50 requests/min. The tool has a 1.2s delay between calls. For batches over 100 leads, consider increasing the delay or splitting runs.
- **Duplicate prevention**: Re-running the workflow for the same query appends only new leads. De-duplication is based on Name + Location (case-insensitive).
- **Perplexity fallback**: If the API call fails for a lead (timeout, rate limit), a basic fallback summary is generated from the business name and category — no data is lost.
- **Cost control**: Always set `max_results` to a reasonable number. Avoid accidentally scraping thousands of places. The tool prints cost-relevant info during execution.

## API Keys Required
| Key | Where to Get It | .env Variable |
|---|---|---|
| Apify API Token | https://console.apify.com/settings/integrations | `APIFY_API_TOKEN` |
| Perplexity API Key | https://www.perplexity.ai/settings/api | `PERPLEXITY_API_KEY` |
