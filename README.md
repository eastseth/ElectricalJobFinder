# Electrical Job Finder

This is a Progressive Web App (PWA) shell for an electrical-technology-focused job search.

## Included
- New Jobs tab
- All Jobs tab with search
- Settings screen showing target roles, Kentucky areas, and monitoring schedule
- Home Screen PWA manifest and icons
- Offline app shell
- JSON job feed (`jobs.json`)
- Browser-notification permission button

## Important
The app UI is functional, but automatic live job discovery requires a hosted backend or automation that writes fresh listings into `jobs.json` (or an API endpoint). The ChatGPT job-watch automation created in the conversation operates separately and can send notifications when it finds new openings.

## Install on iPhone
1. Host this folder on an HTTPS host such as Vercel, Netlify, GitHub Pages, or similar.
2. Open the hosted URL in Safari.
3. Tap Share.
4. Tap Add to Home Screen.

## Job feed format
Edit `jobs.json` using entries like:
{
  "id": "unique-job-id",
  "title": "Electrical Technician",
  "company": "Company Name",
  "location": "Lexington, KY",
  "pay": "$24-$30/hr",
  "posted": "Posted today",
  "reason": "Entry-level electrical maintenance role matching your coursework.",
  "apply_url": "https://..."
}

## Search targets
Electrical Technician, Electrical Maintenance, Electrical Apprentice, Electrician Helper,
Controls Technician, Industrial Maintenance, Instrumentation/Electrical Technician,
Utility/Plant Electrical, and Electrical Internships.


## Candidate-fit rules
This search is tuned for a current Electrical Technology student without professional electrical field experience.

Highest priority:
- Electrical internships
- Electrician helper jobs
- Apprenticeships / apprentice electrician positions
- Electrical trainee positions
- Entry-level electrical technician positions
- Entry-level industrial maintenance jobs with electrical duties
- Controls / instrumentation trainee jobs
- Utility or plant electrical trainee roles
- Jobs offering on-the-job training or accepting 0-1 years of experience

Usually de-prioritized:
- Roles requiring several years of electrical field experience
- Journeyman/master electrician credentials
- Roles requiring a completed bachelor's degree unless equivalent technical education/training is accepted
