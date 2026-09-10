import hashlib
import json
import math
import re
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs


OUTPUT_FILE = Path("jobs.json")

SEARCH_TERMS = [
    "electrical apprentice",
    "electrician helper",
    "electrical internship",
    "electrical technician trainee",
    "industrial maintenance electrical",
    "controls instrumentation trainee",
]

PREFERRED_AREAS = [
    "lexington",
    "georgetown",
    "harrodsburg",
    "danville",
    "nicholasville",
    "lawrenceburg",
    "louisville",
    "kentucky",
]

# Jobs that are generally above the experience level we're targeting.
BAD_TITLE_WORDS = [
    "journeyman",
    "journeyperson",
    "master electrician",
    "senior electrician",
    "senior electrical",
    "lead electrician",
    "electrical supervisor",
    "electrical manager",
    "electrical engineer ii",
    "electrical engineer iii",
]

GOOD_WORDS = [
    "apprentice",
    "apprenticeship",
    "helper",
    "intern",
    "internship",
    "trainee",
    "entry level",
    "entry-level",
    "electrical technician",
    "maintenance technician",
    "industrial maintenance",
    "controls technician",
    "instrumentation",
    "electrical technology",
    "no experience",
]


def clean(value):
    """Turn pandas/NaN values into safe text."""
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    return str(value).strip()


def make_id(job_url, title, company):
    base = job_url or f"{title}|{company}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]


def get_location(row):
    # JobSpy normally provides city/state columns.
    city = clean(row.get("city"))
    state = clean(row.get("state"))

    if city and state:
        return f"{city}, {state}"

    location = clean(row.get("location"))

    if location:
        return location

    return "Kentucky"


def get_pay(row):
    min_amount = row.get("min_amount")
    max_amount = row.get("max_amount")
    interval = clean(row.get("interval")).lower()

    try:
        min_ok = min_amount is not None and not pd.isna(min_amount)
    except Exception:
        min_ok = False

    try:
        max_ok = max_amount is not None and not pd.isna(max_amount)
    except Exception:
        max_ok = False

    if not min_ok and not max_ok:
        return None

    labels = {
        "hourly": "/hr",
        "yearly": "/yr",
        "monthly": "/mo",
        "weekly": "/wk",
        "daily": "/day",
    }

    suffix = labels.get(interval, "")

    def money(number):
        number = float(number)

        if number >= 1000:
            return f"${number:,.0f}"

        if number.is_integer():
            return f"${number:.0f}"

        return f"${number:.2f}"

    if min_ok and max_ok:
        return f"{money(min_amount)}–{money(max_amount)}{suffix}"

    if min_ok:
        return f"From {money(min_amount)}{suffix}"

    return f"Up to {money(max_amount)}{suffix}"


def get_posted(row):
    raw = row.get("date_posted")

    if raw is None:
        return "Recently posted"

    try:
        if pd.isna(raw):
            return "Recently posted"
    except Exception:
        pass

    try:
        if isinstance(raw, datetime):
            posted_date = raw.date()
        elif isinstance(raw, date):
            posted_date = raw
        else:
            posted_date = pd.to_datetime(raw).date()

        days = (date.today() - posted_date).days

        if days <= 0:
            return "Posted today"
        elif days == 1:
            return "Posted yesterday"
        else:
            return f"Posted {days} days ago"

    except Exception:
        return "Recently posted"


def experience_too_high(text):
    text = text.lower()

    # Strong title/description indicators.
    for word in BAD_TITLE_WORDS:
        if word in text:
            return True

    # Catch requirements such as "3 years experience", "5+ years", etc.
    patterns = [
        r"\b([3-9]|[1-9][0-9])\+?\s+years?\s+(?:of\s+)?experience",
        r"\bminimum\s+of\s+([3-9]|[1-9][0-9])\s+years?",
        r"\bat\s+least\s+([3-9]|[1-9][0-9])\s+years?",
    ]

    for pattern in patterns:
        if re.search(pattern, text):
            return True

    return False


def relevance_score(title, description, location):
    title_l = title.lower()
    desc_l = description.lower()
    location_l = location.lower()

    combined = f"{title_l} {desc_l}"

    score = 0

    # Strongly prioritize accessible entry-level roles.
    if "apprentice" in combined or "apprenticeship" in combined:
        score += 10

    if "helper" in combined:
        score += 10

    if "intern" in combined:
        score += 10

    if "trainee" in combined:
        score += 9

    if "entry level" in combined or "entry-level" in combined:
        score += 9

    if "no experience" in combined:
        score += 9

    if "electrical technician" in combined:
        score += 6

    if "industrial maintenance" in combined:
        score += 5

    if "controls" in combined or "instrumentation" in combined:
        score += 4

    if "electrical" in title_l or "electrician" in title_l:
        score += 5

    # Preferred Kentucky areas get a bump.
    for area in PREFERRED_AREAS:
        if area in location_l:
            score += 3
            break

    return score


def fit_reason(title, description):
    text = f"{title} {description}".lower()

    if "intern" in text:
        return "Electrical internship that can build experience while you are still in school."

    if "helper" in text:
        return "Helper position that appears suitable for someone building hands-on electrical experience."

    if "apprentice" in text or "apprenticeship" in text:
        return "Electrical apprenticeship opportunity that matches an early-career electrical technology path."

    if "trainee" in text:
        return "Trainee position intended for someone developing electrical or maintenance skills."

    if "industrial maintenance" in text:
        return "Industrial maintenance role related to your electrical technology coursework."

    if "controls" in text or "instrumentation" in text:
        return "Controls/instrumentation role related to electrical technology and industrial systems."

    if "electrical technician" in text:
        return "Electrical technician position related to your electrical technology training."

    return "Entry-level electrical-related opening that may fit your education and experience level."


def search_jobs():
    frames = []

    for term in SEARCH_TERMS:
        print(f"\nSearching: {term}")

        try:
            jobs = scrape_jobs(
                site_name=[
                    "indeed",
                    "linkedin",
                    "zip_recruiter",
                ],
                search_term=term,
                location="Kentucky",
                distance=100,
                results_wanted=25,
                hours_old=168,
                country_indeed="USA",
                linkedin_fetch_description=False,
                verbose=1,
            )

            if jobs is not None and not jobs.empty:
                print(f"Found {len(jobs)} results for {term}")
                frames.append(jobs)
            else:
                print(f"No results for {term}")

        except Exception as exc:
            # A single job board/search failure should not kill the whole update.
            print(f"Search failed for '{term}': {exc}")

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)


def build_feed(raw_jobs):
    output = []
    seen_ids = set()

    for _, row in raw_jobs.iterrows():
        title = clean(row.get("title"))
        company = clean(row.get("company"))
        description = clean(row.get("description"))

        job_url = (
            clean(row.get("job_url_direct"))
            or clean(row.get("job_url"))
        )

        if not title or not company or not job_url:
            continue

        location = get_location(row)

        combined = f"{title} {description}"

        # Remove jobs obviously above the requested experience level.
        if experience_too_high(combined):
            continue

        score = relevance_score(title, description, location)

        # Require at least some evidence the job is relevant.
        if score < 5:
            continue

        job_id = make_id(job_url, title, company)

        if job_id in seen_ids:
            continue

        seen_ids.add(job_id)

        output.append(
            {
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "pay": get_pay(row),
                "posted": get_posted(row),
                "reason": fit_reason(title, description),
                "apply_url": job_url,
                "_score": score,
            }
        )

    # Best matches first.
    output.sort(key=lambda job: job["_score"], reverse=True)

    # Keep feed manageable on the phone.
    output = output[:150]

    # Internal score doesn't need to appear in jobs.json.
    for job in output:
        job.pop("_score", None)

    return output


def main():
    raw_jobs = search_jobs()

    if raw_jobs.empty:
        print("No jobs were returned. Existing jobs.json will be preserved.")
        return

    feed = build_feed(raw_jobs)

    if not feed:
        print("Jobs were returned, but none passed the entry-level filters.")
        print("Existing jobs.json will be preserved.")
        return

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(feed, file, indent=2, ensure_ascii=False)

    print(f"\nSaved {len(feed)} jobs to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
