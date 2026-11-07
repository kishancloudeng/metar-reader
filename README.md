# ✈️ METAR Reader

A small Flask web app that turns cryptic aviation weather reports (METARs) into plain English.

Type an airport code, get a friendly report:

```
Input:   KJFK 061851Z 18005KT 10SM CLR 21/09 A3012 TEMPO FM1930 TL2100 2SM -RA OVC008
Output:  Clear skies, 70°F (21°C)
         • Wind is 6 mph from the south.
         • Visibility is 10 miles.
         • Temporarily from 19:30 UTC until 21:00 UTC: visibility 2 miles, light rain, overcast at 800 ft.
```

## Features

- Look up the latest METAR for any airport that reports one (`KJFK`, `EGLL`, or just `JFK` for US airports).
- Plain-English headline and summary: sky, temperature, humidity, wind, visibility, weather and clouds.
- Units converted for humans: °F alongside °C, mph instead of knots, miles, feet, inHg alongside hPa.
- Decodes `TEMPO` (temporary) and `BECMG` (becoming) trend groups, and `NOSIG`.
- Flight category badge (VFR / MVFR / IFR / LIFR).
- Handles both US (statute miles, `A3012`) and international (meters, `Q1018`) formats.
- Light and dark mode, mobile friendly, shareable URLs (`/?code=KSFO`).

## Requirements

- Python 3.8 or newer
- Internet access (weather data is fetched live)

## Installation

```bash
git clone <your-repo-url>
cd METAR-READER

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
python app.py
```

Open <http://127.0.0.1:5000> and enter an airport code.

### Configuration

Set these environment variables if needed:

| Variable      | Default     | Purpose                                                  |
|---------------|-------------|----------------------------------------------------------|
| `HOST`        | `127.0.0.1` | Interface to bind. Use `0.0.0.0` to expose on a network. |
| `PORT`        | `5000`      | Port to listen on.                                       |
| `FLASK_DEBUG` | unset       | Set to `1` for auto-reload during development only.      |

> ⚠️ Never run with `FLASK_DEBUG=1` on a public server. The debugger allows remote code execution.

### Deploying publicly

The built-in Flask server is for development. For production use a WSGI server:

```bash
pip install gunicorn
gunicorn --workers 2 --bind 0.0.0.0:8000 app:app
```

Put it behind a reverse proxy (nginx, Caddy, or your platform's router) with HTTPS.

## How it works

| File                    | Role                                                              |
|-------------------------|-------------------------------------------------------------------|
| `app.py`                | Flask route; validates input, fetches the METAR, renders the page |
| `metar_decoder.py`      | Parses raw METAR text and produces the plain-English report       |
| `templates/index.html`  | The single-page UI                                                |

Data comes from the [NOAA Aviation Weather Center](https://aviationweather.gov/data/api/) API. To use a different
source, change `METAR_URL` in `app.py`. It must accept `?ids=<ICAO>` and return raw METAR text.

## Limitations

- Remarks (`RMK ...`) are shown as raw text but not decoded.
- `PROB30`/`PROB40` probability groups and runway visual range (`R04L/...`) are not decoded.
- Flight category follows US FAA thresholds.

## ⚠️ Disclaimer

This tool is for general interest only. **Do not use it for flight planning or any safety-critical decision.**
Always use official sources and briefings.
