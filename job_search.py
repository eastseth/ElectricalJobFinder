import hashlib
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
from jobspy import scrape_jobs


OUTPUT_FILE = Path("jobs.json")
STATUS_FILE = Path("status.json")
MAX_FEED_SIZE = 250
MAX_JOB_AGE_DAYS = 45

SEARCH_TERMS = [
    "electrician",
    "electrical apprentice",
    "electrician helper",
    "electrical internship",
    "electrical technician",
    "electrical maintenance",
    "industrial electrician",
    "controls technician",
    "instrumentation technician",
    "maintenance technician electrical",
]

# Broader statewide search, plus tighter city searches that job boards
# often rank more completely than a generic "Kentucky" query.
SEARCHES = [
    *(
        {
            "term": term,
            "location": "Kentucky",
            "distance": 200,
            "sites": ["indeed", "linkedin", "zip_recruiter", "google"],
        }
        for term in SEARCH_TERMS
    ),
    *(
        {
            "term": term,
            "location": location,
            "distance": distance,
            "sites": ["indeed"],
        }
        for term in [
            "electrician",
            "electrical apprentice",
            "electrician helper",
            "electrical technician",
        ]
        for location, distance in (("Lexington, KY", 60), ("Louisville, KY", 45))
    ),
]

PREFERRED_AREAS = [
    "lexington",
    "georgetown",
    "harrodsburg",
    "danville",
    "nicholasville",
    "lawrenceburg",
    "louisville",
    "frankfort",
    "richmond",
    "versailles",
    "winchester",
    "paris",
    "berea",
    "shelbyville",
    "bardstown",
    "elizabethtown",
    "bowling green",
    "covington",
    "florence",
    "kentucky",
]

ENTRY_TITLE_WORDS = [
    "apprentice",
    "apprenticeship",
    "helper",
    "intern",
    "internship",
    "trainee",
    "entry level",
    "entry-level",
    "no experience",
]

# Only applied to job titles. Descriptions often mention journeymen
# even for apprentice/helper openings.
BAD_TITLE_WORDS = [
    "journeyman",
    "journeyperson",
    "master electrician",
    "licensed electrician",
    "licensed master",
    "senior electrician",
    "senior electrical",
    "lead electrician",
    "electrical supervisor",
    "electrical manager",
    "electrical engineer ii",
    "electrical engineer iii",
    "foreman",
    "superintendent",
]

SENIOR_TITLE_RE = re.compile(
    r"\b(managers?|directors?|supervisors?|superintendents?|foremen|foreman|chief|leaders?|leads?|executive|principal|estimator)\b",
    re.I,
)

TITLE_EXCLUSIONS = [
    "diesel",
    "software",
    "nurse",
    "nursing",
    "sales associate",
    "sales specialist",
    "truck driver",
    "cdl driver",
]

ELECTRICAL_MARKERS = [
    "electric",
    "controls",
    "instrumentation",
    "i&e",
    "i & e",
    "i/e",
    "plc",
    "switchgear",
    "substation",
    "lineman",
    "lineworker",
    "line worker",
    "wireman",
    "high voltage",
    "low voltage",
    "motor control",
]

TARGET_TITLE_WORDS = [
    "electric",
    "apprentice",
    "helper",
    "trainee",
    "technician",
    "maintenance",
    "controls",
    "instrumentation",
    "lineman",
    "lineworker",
    "line worker",
    "wireman",
    "i&e",
    "i/e",
    "substation",
    "co-op",
    "coop",
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
    "electrician",
    "electrical",
]

OTHER_STATES = re.compile(
    r",\s*(OH|TN|IN|IL|WV|MO|VA|NC|SC|GA|AL|MS|AR|PA|NY|TX|FL|CA|MI|WI)\b",
    re.I,
)


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


def normalize_key(value):
    return re.sub(r"[^a-z0-9]+", "", clean(value).lower())


def make_id(job_url, title, company):
    base = job_url or f"{title}|{company}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:20]


def make_dedupe_key(title, company):
    return f"{normalize_key(title)}|{normalize_key(company)}"


def get_location(row):
    city = clean(row.get("city"))
    state = clean(row.get("state"))

    if city and state:
        return f"{city}, {state}"

    location = clean(row.get("location"))
    if location:
        return location

    return "Kentucky"


def parse_posted_date(raw):
    if raw is None:
        return None

    try:
        if pd.isna(raw):
            return None
    except Exception:
        pass

    try:
        if isinstance(raw, datetime):
            return raw.date()
        if isinstance(raw, date):
            return raw
        parsed = pd.to_datetime(raw, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


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


def format_posted(posted_date):
    if posted_date is None:
        return "Recently posted"

    days = (date.today() - posted_date).days

    if days <= 0:
        return "Posted today"
    if days == 1:
        return "Posted yesterday"
    return f"Posted {days} days ago"


def has_intern(text):
    return re.search(r"\bintern(?:s|ship)?\b", text.lower()) is not None


def is_entry_title(title):
    title_l = title.lower()
    if has_intern(title_l):
        return True
    return any(word in title_l for word in ENTRY_TITLE_WORDS if "intern" not in word)


def experience_too_high(title, description):
    title_l = title.lower()
    description_l = description.lower()

    for word in BAD_TITLE_WORDS:
        if word in title_l:
            return True

    # Apprentice/helper/intern posts often mention journeymen they will work under.
    if is_entry_title(title):
        return False

    if SENIOR_TITLE_RE.search(title_l):
        return True

    if re.search(r"\bclass a\b", title_l) and "lineman" in title_l:
        return True

    if "engineer" in title_l and not is_entry_title(title) and "co-op" not in title_l and "coop" not in title_l:
        if "technician" not in title_l and "technologist" not in title_l:
            return True

    combined = f"{title_l} {description_l}"
    patterns = [
        r"\b([3-9]|[1-9][0-9])\+?\s+years?\s+(?:of\s+)?experience",
        r"\bminimum\s+of\s+([3-9]|[1-9][0-9])\s+years?",
        r"\bat\s+least\s+([3-9]|[1-9][0-9])\s+years?",
    ]

    return any(re.search(pattern, combined) for pattern in patterns)


def is_target_role_title(title):
    title_l = title.lower()
    if has_intern(title_l):
        return True
    return any(word in title_l for word in TARGET_TITLE_WORDS)


def is_electrical_related(title, description, company):
    if not is_target_role_title(title):
        return False

    title_l = title.lower()
    company_l = company.lower()
    title_company = f"{title_l} {company_l}"

    if any(word in title_l for word in TITLE_EXCLUSIONS):
        return False

    intern_like = has_intern(title_l) or "co-op" in title_l or "coop" in title_l
    if intern_like and not any(marker in title_company for marker in ELECTRICAL_MARKERS):
        return False

    if any(marker in title_company for marker in ELECTRICAL_MARKERS):
        return True

    if any(
        phrase in title_l
        for phrase in (
            "maintenance technician",
            "industrial maintenance",
            "controls technician",
            "automation technician",
        )
    ):
        return True

    return any(marker in description.lower() for marker in ELECTRICAL_MARKERS)


def in_target_area(location):
    loc = location.lower()

    if "kentucky" in loc or re.search(r"\bky\b", loc):
        return True

    if OTHER_STATES.search(location):
        return False

    if loc in ("", "kentucky", "united states", "usa"):
        return True

    return any(area in loc for area in PREFERRED_AREAS)


def relevance_score(title, description, location):
    title_l = title.lower()
    desc_l = description.lower() if is_target_role_title(title) else ""
    location_l = location.lower()
    combined = f"{title_l} {desc_l}"

    score = 0

    if "apprentice" in combined or "apprenticeship" in combined:
        score += 10

    if "helper" in combined:
        score += 10

    if has_intern(combined) or "co-op" in combined or "coop" in combined:
        score += 10

    if "trainee" in combined:
        score += 9

    if "entry level" in combined or "entry-level" in combined:
        score += 9

    if "no experience" in combined:
        score += 9

    if "electrical technician" in combined:
        score += 6

    if "maintenance technician" in combined:
        score += 5

    if "industrial maintenance" in combined:
        score += 5

    if "controls technician" in combined:
        score += 6

    if "controls" in combined or "instrumentation" in combined:
        score += 4

    if "electrician" in title_l:
        score += 6

    if "electrical" in title_l:
        score += 5

    if "lineman" in title_l or "lineworker" in title_l or "line worker" in title_l:
        score += 5

    for word in GOOD_WORDS:
        if word == "intern":
            if has_intern(combined):
                score += 1
            continue
        if word in combined:
            score += 1

    if "kentucky" in location_l or re.search(r"\bky\b", location_l):
        score += 3
    else:
        for area in PREFERRED_AREAS:
            if area in location_l:
                score += 3
                break

    return score


def fit_reason(title, description):
    text = f"{title} {description}".lower()

    if has_intern(text):
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

    if "electrician" in text:
        return "Electrician opening in Kentucky that may fit an electrical technology student building field experience."

    return "Entry-level electrical-related opening that may fit your education and experience level."


def google_term_for(term, location):
    where = location if "," in location else f"{location}, USA"
    return f"{term} jobs near {where} posted this month"


def search_jobs():
    frames = []
    errors = []

    for index, search in enumerate(SEARCHES):
        term = search["term"]
        location = search["location"]
        print(f"\nSearching: {term} @ {location} ({', '.join(search['sites'])})")

        try:
            jobs = scrape_jobs(
                site_name=search["sites"],
                search_term=term,
                google_search_term=google_term_for(term, location),
                location=location,
                distance=search["distance"],
                results_wanted=50,
                hours_old=336,
                country_indeed="USA",
                linkedin_fetch_description=False,
                verbose=1,
            )

            if jobs is not None and not jobs.empty:
                print(f"Found {len(jobs)} results for {term} @ {location}")
                frames.append(jobs)
            else:
                print(f"No results for {term} @ {location}")

        except Exception as exc:
            message = f"{term} @ {location}: {exc}"
            print(f"Search failed for {message}")
            errors.append(message)

        if index < len(SEARCHES) - 1:
            time.sleep(1)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return combined, errors


def row_to_job(row):
    title = clean(row.get("title"))
    company = clean(row.get("company")) or "See listing"
    description = clean(row.get("description"))
    job_url = clean(row.get("job_url_direct")) or clean(row.get("job_url"))

    if not title or not job_url:
        return None, "missing_fields"

    location = get_location(row)

    if not in_target_area(location):
        return None, "out_of_area"

    if not is_electrical_related(title, description, company):
        return None, "not_electrical"

    if experience_too_high(title, description):
        return None, "too_senior"

    score = relevance_score(title, description, location)
    if score < 4:
        return None, "low_score"

    posted_date = parse_posted_date(row.get("date_posted"))
    if posted_date and (date.today() - posted_date).days > MAX_JOB_AGE_DAYS:
        return None, "too_old"

    return {
        "id": make_id(job_url, title, company),
        "title": title,
        "company": company,
        "location": location,
        "pay": get_pay(row),
        "posted": format_posted(posted_date),
        "date_posted": posted_date.isoformat() if posted_date else None,
        "reason": fit_reason(title, description),
        "apply_url": job_url,
        "source": clean(row.get("site")) or None,
        "_score": score,
        "_dedupe": make_dedupe_key(title, company),
    }, None


def build_feed(raw_jobs):
    output = []
    seen_ids = set()
    seen_jobs = set()
    stats = {
        "missing_fields": 0,
        "out_of_area": 0,
        "not_electrical": 0,
        "too_senior": 0,
        "low_score": 0,
        "too_old": 0,
        "duplicate": 0,
        "kept": 0,
    }

    for _, row in raw_jobs.iterrows():
        job, reason = row_to_job(row)

        if job is None:
            stats[reason] = stats.get(reason, 0) + 1
            continue

        if job["id"] in seen_ids or job["_dedupe"] in seen_jobs:
            stats["duplicate"] += 1
            continue

        seen_ids.add(job["id"])
        seen_jobs.add(job["_dedupe"])
        stats["kept"] += 1
        output.append(job)

    return output, stats


def load_existing_jobs():
    if not OUTPUT_FILE.exists():
        return []

    try:
        data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(data, list):
        return []

    kept = []
    for job in data:
        if not isinstance(job, dict):
            continue
        if job.get("id") == "example-1":
            continue
        if "example" in clean(job.get("company")).lower():
            continue
        if not job.get("title") or not job.get("apply_url"):
            continue

        location = clean(job.get("location")) or "Kentucky"
        title = clean(job.get("title"))
        company = clean(job.get("company")) or "See listing"
        description = clean(job.get("reason"))

        if not in_target_area(location):
            continue
        if not is_electrical_related(title, description, company):
            continue
        if experience_too_high(title, description):
            continue

        posted_date = parse_posted_date(job.get("date_posted"))
        if posted_date and (date.today() - posted_date).days > MAX_JOB_AGE_DAYS:
            continue

        job = dict(job)
        job["company"] = company
        job["posted"] = format_posted(posted_date)
        job["_score"] = relevance_score(title, description, location)
        job["_dedupe"] = make_dedupe_key(title, company)
        kept.append(job)

    return kept


def merge_jobs(fresh, existing):
    merged = []
    seen_ids = set()
    seen_jobs = set()

    for job in list(fresh) + list(existing):
        job_id = job.get("id")
        dedupe = job.get("_dedupe") or make_dedupe_key(job.get("title", ""), job.get("company", ""))

        if not job_id or job_id in seen_ids or dedupe in seen_jobs:
            continue

        seen_ids.add(job_id)
        seen_jobs.add(dedupe)
        merged.append(job)

    merged.sort(key=lambda job: job.get("_score", 0), reverse=True)
    merged = merged[:MAX_FEED_SIZE]

    for job in merged:
        job.pop("_score", None)
        job.pop("_dedupe", None)

    return merged


def write_status(payload):
    STATUS_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main():
    status = {
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ok": False,
        "raw_count": 0,
        "saved_count": 0,
        "errors": [],
        "filters": {},
        "message": "",
    }

    try:
        raw_jobs, errors = search_jobs()
        status["errors"] = errors
        status["raw_count"] = 0 if raw_jobs.empty else int(len(raw_jobs))

        existing = load_existing_jobs()
        fresh, filters = build_feed(raw_jobs) if not raw_jobs.empty else ([], {})
        status["filters"] = filters

        if raw_jobs.empty and not existing:
            status["message"] = "No jobs were returned. Existing jobs.json will be preserved."
            print(status["message"])
            return

        feed = merge_jobs(fresh, existing)

        if not feed:
            status["message"] = "Jobs were returned, but none passed the entry-level filters."
            print(status["message"])
            print("Existing jobs.json will be preserved.")
            return

        with OUTPUT_FILE.open("w", encoding="utf-8") as file:
            json.dump(feed, file, indent=2, ensure_ascii=False)

        status["ok"] = True
        status["saved_count"] = len(feed)
        status["message"] = f"Saved {len(feed)} jobs to {OUTPUT_FILE}"
        print(f"\n{status['message']}")

    except Exception as exc:
        status["message"] = f"Job search crashed: {exc}"
        status["errors"] = status.get("errors", []) + [str(exc)]
        print(status["message"])
        raise

    finally:
        write_status(status)


if __name__ == "__main__":
    main()
