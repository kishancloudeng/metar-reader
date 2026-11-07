"""METAR Reader: a small Flask app that turns raw METAR reports into plain English.

The user enters an airport code, the app fetches the latest METAR from the
NOAA Aviation Weather Center and renders a friendly, decoded report.

Run locally with ``python app.py`` or in production with a WSGI server, e.g.
``gunicorn app:app``.
"""
import os
import re

import requests
from flask import Flask, render_template, request

from metar_decoder import decode

# Base URL of the METAR service. Any service that accepts ``?ids=<ICAO>`` and
# returns raw METAR text can be substituted here.
METAR_URL = "https://aviationweather.gov/api/data/metar"

# Seconds to wait for the upstream service before giving up.
REQUEST_TIMEOUT = 10

# Accepts 3-4 letter/digit airport identifiers (e.g. JFK, KJFK, EGLL).
AIRPORT_CODE_RE = re.compile(r"[A-Z0-9]{3,4}")

app = Flask(__name__)


def fetch_metar(icao):
    """Fetch the latest raw METAR for an airport.

    Args:
        icao: Four-character ICAO station identifier, e.g. ``"KJFK"``.

    Returns:
        The raw METAR string, or ``None`` if the service has no report for
        that station.

    Raises:
        requests.RequestException: If the service is unreachable, times out,
            or returns an HTTP error.
    """
    response = requests.get(
        METAR_URL,
        params={"ids": icao, "format": "raw"},
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "metar-reader-flask"},
    )
    response.raise_for_status()
    text = response.text.strip()
    # The service may return several lines; the first is the latest report.
    return text.splitlines()[0] if text else None


def normalize_code(code):
    """Convert user input to an ICAO station identifier.

    US airports are commonly typed as three letters (``JFK``) but METAR
    stations use four (``KJFK``), so a ``K`` prefix is added to 3-character
    codes. Four-character codes are assumed to be ICAO already.
    """
    return "K" + code if len(code) == 3 else code


@app.route("/")
def index():
    """Render the search page and, if a code was submitted, the decoded METAR.

    The airport code is read from the ``code`` query parameter. A GET form is
    used so that results are shareable and bookmarkable by URL.
    """
    code = request.args.get("code", "").strip().upper()
    result = error = None

    if code:
        # Validate before making any network request; this also keeps
        # arbitrary user input out of the upstream query string.
        if not AIRPORT_CODE_RE.fullmatch(code):
            error = "Please enter a 3–4 letter airport code, e.g. KJFK or KSFO."
        else:
            icao = normalize_code(code)
            try:
                raw = fetch_metar(icao)
            except requests.RequestException:
                error = "Couldn't reach the weather service. Please try again shortly."
            else:
                if raw:
                    result = decode(raw)
                else:
                    error = f"No METAR found for {icao}. Check the code and try again."

    return render_template("index.html", code=code, result=result, error=error)


if __name__ == "__main__":
    # Debug mode exposes an interactive debugger that allows remote code
    # execution, so it is opt-in (FLASK_DEBUG=1) and never on by default.
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
    )
