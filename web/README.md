# JalMaapi dashboard (P4)

Static single-page app: `index.html`, `styles.css`, `app.js`. No build step, no Node. Chart.js and Leaflet
come from cdnjs; fonts from Google Fonts.

Run locally against mock data:

    cd web && python3 -m http.server 8080    # open http://localhost:8080/?mock=1

Against the API: serve `web/` from FastAPI (`app.mount("/", StaticFiles(directory="web", html=True))` after the
API routes) or deploy to Amplify Hosting with `amplify.yml` and open `?api=https://<app-runner-url>`.

Regenerate mock data from the physics model: `.venv/bin/python web/make_mock_data.py --minutes-in 25`.

Views: City (map + ranked sites), Site (frame, heatmap, verdict cards, forecast band, what-if pumps, drain
health), Approvals (officer queue, Approve / Reject with officer id, bilingual advisory), Pumps (forecast-based
allocation vs the nearest-pump baseline), Drain health, Feed. Simulated data is labelled everywhere; assumed
thresholds (two-wheeler, bus/truck) are labelled "assumed".
