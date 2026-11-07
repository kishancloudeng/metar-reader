"""Decode a raw METAR string into plain English."""
import re

COMPASS = ["north", "north-northeast", "northeast", "east-northeast", "east",
           "east-southeast", "southeast", "south-southeast", "south",
           "south-southwest", "southwest", "west-southwest", "west",
           "west-northwest", "northwest", "north-northwest"]

INTENSITY = {"-": "light", "+": "heavy", "VC": "nearby"}
DESCRIPTORS = {"MI": "shallow", "PR": "partial", "BC": "patchy", "DR": "drifting",
               "BL": "blowing", "SH": "showers of", "TS": "thunderstorm with",
               "FZ": "freezing"}
PHENOMENA = {"DZ": "drizzle", "RA": "rain", "SN": "snow", "SG": "snow grains",
             "IC": "ice crystals", "PL": "ice pellets", "GR": "hail",
             "GS": "small hail", "UP": "unknown precipitation", "BR": "mist",
             "FG": "fog", "FU": "smoke", "VA": "volcanic ash", "DU": "dust",
             "SA": "sand", "HZ": "haze", "PY": "spray", "PO": "dust whirls",
             "SQ": "squalls", "FC": "funnel cloud", "SS": "sandstorm",
             "DS": "duststorm"}
COVER = {"FEW": "a few clouds", "SCT": "scattered clouds",
         "BKN": "broken clouds (mostly cloudy)", "OVC": "overcast"}

WX_RE = re.compile(r"^(\+|-|VC)?((?:MI|PR|BC|DR|BL|SH|TS|FZ)?)((?:%s)+)$"
                   % "|".join(PHENOMENA))


def _c_to_f(c):
    return c * 9 / 5 + 32


def _temp(token):
    neg = token.startswith("M")
    v = int(token.lstrip("M"))
    return -v if neg else v


def _fmt_temp(c):
    return f"{round(_c_to_f(c))}°F ({c}°C)"


def _wind_dir(deg):
    return COMPASS[round(deg / 22.5) % 16]


def _kt_to_mph(kt):
    return round(kt * 1.15078)


def _decode_wx(token):
    m = WX_RE.match(token)
    if not m:
        return None
    inten, desc, phen = m.groups()
    codes = [phen[i:i + 2] for i in range(0, len(phen), 2)]
    words = " and ".join(PHENOMENA[c] for c in codes)
    parts = [INTENSITY.get(inten, ""), DESCRIPTORS.get(desc, ""), words]
    return " ".join(p for p in parts if p)


def _sky_summary(layers):
    if not layers:
        return None
    covers = [c for c, _ in layers]
    if covers == ["CLR"] or covers == ["SKC"] or covers == ["NCD"] or covers == ["NSC"]:
        return "Clear skies"
    if "OVC" in covers:
        top = "overcast"
    elif "BKN" in covers:
        top = "mostly cloudy"
    elif "SCT" in covers:
        top = "partly cloudy"
    else:
        top = "mostly clear with a few clouds"
    return top[0].upper() + top[1:]


def decode(raw):
    """Decode a raw METAR string into a plain-English report.

    Returns a dict with: station, headline, summary (list of sentences),
    details (list of (label, value)), flight_category, trends (list of
    sentences for TEMPO/BECMG/NOSIG groups), remarks and raw.
    """
    tokens = raw.replace("=", "").split()
    kind = None
    if tokens and tokens[0] in ("METAR", "SPECI"):
        kind = tokens.pop(0)
    station = tokens.pop(0) if tokens else "?"

    body, trend_groups, remarks = _split_sections(tokens)

    d = {"station": station, "special": kind == "SPECI", "raw": raw,
         "wx": [], "layers": []}
    _parse_group(body, d)

    result = _describe(d, remarks)
    result["trends"] = _describe_trends(trend_groups)
    return result


def _split_sections(tokens):
    """Split tokens into (current conditions, trend groups, remarks).

    Trend groups are (keyword, tokens) pairs for TEMPO / BECMG / NOSIG. They
    must be separated from the main body, otherwise a forecast such as
    "TEMPO 1SM FG" would overwrite the current visibility.
    """
    body, groups, remarks = [], [], []
    current = body
    for i, t in enumerate(tokens):
        if t == "RMK":
            remarks = tokens[i + 1:]
            break
        if t in ("TEMPO", "BECMG"):
            current = []
            groups.append((t, current))
        elif t == "NOSIG":
            groups.append((t, []))
            current = []
        else:
            current.append(t)
    return body, groups, remarks


def _parse_group(tokens, d):
    """Parse weather tokens (a METAR body or one trend group) into dict d."""
    for t in tokens:
        if re.fullmatch(r"\d{6}Z", t):
            d["day"], d["hour"], d["minute"] = int(t[:2]), t[2:4], t[4:6]
        elif t in ("AUTO", "COR"):
            d["auto"] = t == "AUTO"
        elif (m := re.fullmatch(r"(FM|TL|AT)(\d{2})(\d{2})", t)):
            d.setdefault("times", []).append((m[1], f"{m[2]}:{m[3]}"))
        elif t == "NSW":
            d["nsw"] = True
        elif (m := re.fullmatch(r"(VRB|\d{3})(\d{2,3})(?:G(\d{2,3}))?(KT|MPS)", t)):
            mult = 1.94384 if m[4] == "MPS" else 1
            d["wind"] = (m[1], round(int(m[2]) * mult),
                         round(int(m[3]) * mult) if m[3] else None)
        elif (m := re.fullmatch(r"(\d{3})V(\d{3})", t)):
            d["wind_var"] = (int(m[1]), int(m[2]))
        elif (m := re.fullmatch(r"(M)?(\d+(?:/\d+)?|\d+ \d+/\d+)SM", t)) or t == "P6SM":
            d["vis"] = 6.5 if t == "P6SM" else _frac(m[2])
            d["vis_over"] = t == "P6SM"
        elif t.isdigit() and len(t) == 1:
            # Whole-mile part of a mixed fraction such as "1 1/2SM".
            d["_whole"] = int(t)
        elif re.fullmatch(r"\d{4}", t) and "vis" not in d:
            # Metric visibility in meters (international reports).
            d["vis"] = int(t) / 1609.34
            d["vis_over"] = t == "9999"
        elif t == "CAVOK":
            d["cavok"] = True
        elif (m := re.fullmatch(r"(FEW|SCT|BKN|OVC)(\d{3})(CB|TCU)?", t)):
            d["layers"].append((m[1], int(m[2]) * 100, m[3]))
        elif t in ("CLR", "SKC", "NCD", "NSC"):
            d["clear"] = True
        elif (m := re.fullmatch(r"VV(\d{3})", t)):
            d["vv"] = int(m[1]) * 100
        elif (m := re.fullmatch(r"(M?\d{2})/(M?\d{2})?", t)):
            d["temp"] = _temp(m[1])
            d["dew"] = _temp(m[2]) if m[2] else None
        elif (m := re.fullmatch(r"A(\d{4})", t)):
            d["altim_in"] = int(m[1]) / 100
        elif (m := re.fullmatch(r"Q(\d{4})", t)):
            d["altim_hpa"] = int(m[1])
        else:
            w = _decode_wx(t)
            if w:
                d["wx"].append(w)

    if "_whole" in d and "vis" in d:
        d["vis"] += d.pop("_whole")


def _describe_trends(groups):
    """Turn TEMPO/BECMG/NOSIG groups into plain-English sentences."""
    lead = {"TEMPO": "Temporarily", "BECMG": "Becoming"}
    when = {"FM": "from", "TL": "until", "AT": "at"}
    out = []
    for keyword, tokens in groups:
        if keyword == "NOSIG":
            out.append("No significant change is expected in the next two hours.")
            continue
        g = {"wx": [], "layers": []}
        _parse_group(tokens, g)

        parts = []
        if g.get("cavok"):
            parts.append("clear skies and good visibility")
        if "wind" in g:
            direction, spd, gust = g["wind"]
            mph = _kt_to_mph(spd)
            if spd == 0:
                parts.append("calm winds")
            elif direction == "VRB":
                parts.append(f"light and variable wind at {mph} mph")
            else:
                parts.append(f"wind {mph} mph from the {_wind_dir(int(direction))}")
            if gust and spd:
                parts[-1] += f", gusting to {_kt_to_mph(gust)} mph"
        if "vis" in g:
            v = g["vis"]
            parts.append("visibility more than 6 miles" if g.get("vis_over")
                         else f"visibility {v:.1f} miles".replace(".0 ", " "))
        if g["wx"]:
            parts.append(", ".join(g["wx"]))
        if g.get("nsw"):
            parts.append("no significant weather")
        if g.get("clear"):
            parts.append("clear skies")
        for cover, ft, _ in g["layers"]:
            parts.append(f"{COVER[cover]} at {ft:,} ft")
        if "vv" in g:
            parts.append(f"sky obscured (vertical visibility {g['vv']:,} ft)")

        times = " ".join(f"{when[k]} {v} UTC" for k, v in g.get("times", []))
        head = lead[keyword] + (f" {times}" if times else "")
        out.append(f"{head}: {', '.join(parts) if parts else 'conditions change'}.")
    return out


def _frac(s):
    if "/" in s:
        a, b = s.split("/")
        return int(a) / int(b)
    return float(s)


def _describe(d, remarks):
    summary, details = [], []

    # Sky headline
    if d.get("cavok"):
        sky = "Clear skies"
    elif d.get("clear"):
        sky = "Clear skies"
    elif "vv" in d:
        sky = "Sky obscured"
    elif d["layers"]:
        sky = _sky_summary([(c, h) for c, h, _ in d["layers"]])
    else:
        sky = "Sky conditions not reported"

    parts = [sky]
    if d["wx"]:
        parts.append(", ".join(d["wx"]))
    if "temp" in d:
        parts.append(_fmt_temp(d["temp"]))
    headline = ", ".join(parts)

    # Temperature / humidity feel
    if "temp" in d:
        s = f"It's {_fmt_temp(d['temp'])}"
        if d.get("dew") is not None:
            rh = _humidity(d["temp"], d["dew"])
            s += f" with a dew point of {_fmt_temp(d['dew'])} (about {rh}% humidity)"
            details.append(("Humidity", f"~{rh}%"))
        summary.append(s + ".")
        details.append(("Temperature", _fmt_temp(d["temp"])))
        if d.get("dew") is not None:
            details.append(("Dew point", _fmt_temp(d["dew"])))

    # Wind
    if "wind" in d:
        direction, spd, gust = d["wind"]
        mph = _kt_to_mph(spd)
        if spd == 0:
            w = "Winds are calm"
            details.append(("Wind", "Calm"))
        else:
            if direction == "VRB":
                w = f"Wind is light and variable at {mph} mph"
                details.append(("Wind", f"Variable, {mph} mph"))
            else:
                deg = int(direction)
                w = f"Wind is {mph} mph from the {_wind_dir(deg)}"
                details.append(("Wind", f"{mph} mph from {deg}° ({_wind_dir(deg)})"))
            if gust:
                w += f", gusting to {_kt_to_mph(gust)} mph"
            if "wind_var" in d:
                a, b = d["wind_var"]
                w += f" (direction varying between {_wind_dir(a)} and {_wind_dir(b)})"
        summary.append(w + ".")

    # Visibility
    if "vis" in d:
        v = d["vis"]
        txt = "more than 6 miles" if d.get("vis_over") else \
              f"{v:g} mile{'s' if v != 1 else ''}"
        summary.append(f"Visibility is {txt}.")
        details.append(("Visibility", txt))
    elif d.get("cavok"):
        summary.append("Visibility is 6+ miles (CAVOK).")

    # Weather
    if d["wx"]:
        summary.append("Current weather: " + ", ".join(d["wx"]) + ".")
        details.append(("Weather", ", ".join(d["wx"])))

    # Clouds
    if d["layers"]:
        desc = []
        for cover, ft, kind in d["layers"]:
            s = f"{COVER[cover]} at {ft:,} ft"
            if kind == "CB":
                s += " (cumulonimbus – thunderstorm clouds)"
            elif kind == "TCU":
                s += " (towering cumulus)"
            desc.append(s)
        details.append(("Clouds", "; ".join(desc)))
        summary.append("Clouds: " + "; ".join(desc) + ".")
    elif "vv" in d:
        details.append(("Vertical visibility", f"{d['vv']:,} ft"))
        summary.append(f"The sky is obscured; vertical visibility is {d['vv']:,} ft.")

    # Pressure
    if "altim_in" in d:
        hpa = round(d["altim_in"] * 33.8639)
        details.append(("Pressure", f"{d['altim_in']:.2f} inHg ({hpa} hPa)"))
    elif "altim_hpa" in d:
        details.append(("Pressure", f"{d['altim_hpa']} hPa ({d['altim_hpa'] / 33.8639:.2f} inHg)"))

    # Flight category (US rules)
    cat = _flight_category(d)
    if cat:
        details.append(("Flight category", cat))

    if "day" in d:
        details.append(("Observed", f"Day {d['day']} at {d['hour']}:{d['minute']} UTC"))

    return {"station": d["station"], "headline": headline, "summary": summary,
            "details": details, "flight_category": cat, "raw": d["raw"],
            "remarks": " ".join(remarks)}


def _humidity(t, td):
    import math
    a, b = 17.625, 243.04
    return round(100 * math.exp(a * td / (b + td)) / math.exp(a * t / (b + t)))


def _flight_category(d):
    ceiling = None
    for cover, ft, _ in d["layers"]:
        if cover in ("BKN", "OVC"):
            ceiling = ft if ceiling is None else min(ceiling, ft)
    if "vv" in d:
        ceiling = d["vv"]
    vis = d.get("vis", 10 if d.get("cavok") else None)
    if vis is None and ceiling is None:
        return None
    vis = 10 if vis is None else vis
    c = 99999 if ceiling is None else ceiling
    if vis < 1 or c < 500:
        return "LIFR (low instrument conditions)"
    if vis < 3 or c < 1000:
        return "IFR (instrument conditions)"
    if vis <= 5 or c <= 3000:
        return "MVFR (marginal visual conditions)"
    return "VFR (good visual conditions)"
