"""
test_voice.py - tests for voice.py and the /api/voice endpoint.

Run from the project folder with:
    pytest -v test_voice.py
"""

import os
import re
import string
import tempfile

import pytest

# Use a temporary SQLite database when this file is run on its own.
# (When the whole suite runs, test_app.py has already set one.)
if "SQLITE_DB" not in os.environ:
    _tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    _tmp.close()
    os.environ["SQLITE_DB"] = _tmp.name
os.environ.pop("DATABASE_URL", None)

from app import app
from translations import LANGS, TEXT
from voice import (SPEECH_LANG, VOICE_TEXT, _km, build_script,
                   no_route_script, spoken_minutes)


def holes(text):
    return {n for _, n, _, _ in string.Formatter().parse(text) if n}


ROUTE = ["Kundu River Bank", "Railway Station", "Evacuation Center"]
LEGS = [
    {"from": "Kundu River Bank", "to": "Railway Station",
     "distance": 1.8, "risk": 50, "weight": 51.8},
    {"from": "Railway Station", "to": "Evacuation Center",
     "distance": 2.0, "risk": 0, "weight": 2.0},
]
ETA = {"car": 12.4, "walk": 62.0, "truck": 9.0}


# =========================================================
# TEXT TABLES
# =========================================================
class TestVoiceText:
    def test_every_language_has_every_key(self):
        for lang in ("te", "hi"):
            assert set(VOICE_TEXT[lang]) == set(VOICE_TEXT["en"]), lang

    def test_placeholders_match_english(self):
        for lang in ("te", "hi"):
            for key, text in VOICE_TEXT[lang].items():
                assert holes(text) == holes(VOICE_TEXT["en"][key]), \
                    f"{lang}.{key}"

    def test_every_language_has_a_speech_code(self):
        assert set(SPEECH_LANG) == set(LANGS)

    def test_page_text_for_voice_buttons_exists_everywhere(self):
        keys = [k for k in TEXT["en"] if k.startswith("voice_")]
        assert keys, "voice_* phrases are missing from translations.py"
        for lang in ("te", "hi"):
            for key in keys:
                assert key in TEXT[lang], f"{lang}.{key}"


# =========================================================
# SCRIPT BUILDER
# =========================================================
class TestBuildScript:
    def test_english_script_has_every_part(self):
        script = build_script("en", ROUTE, 3.8, ETA, "Moderate risk", LEGS)
        text = script["text"]
        assert script["speech_lang"] == "en-IN"
        assert "Kundu River Bank" in text and "Evacuation Center" in text
        assert "3.8 kilometres" in text
        assert "Moderate risk" in text
        assert "Caution" in text                   # the high-flood road
        assert "12 minutes by car" in text
        assert text.startswith(script["sentences"][0])

    def test_caution_only_for_flooded_roads(self):
        dry = [dict(leg, risk=0) for leg in LEGS]
        script = build_script("en", ROUTE, 3.8, ETA, "Very safe", dry)
        assert "Caution" not in script["text"]

    def test_medium_flood_also_gets_a_caution(self):
        legs = [dict(leg, risk=10) for leg in LEGS]
        text = build_script("en", ROUTE, 3.8, ETA, "Low risk", legs)["text"]
        assert text.count("Caution") == 2

    def test_telugu_and_hindi_use_their_own_script(self):
        te = build_script("te", ROUTE, 3.8, ETA, "High risk", LEGS)
        hi = build_script("hi", ROUTE, 3.8, ETA, "High risk", LEGS)
        assert te["speech_lang"] == "te-IN"
        assert hi["speech_lang"] == "hi-IN"
        assert re.search("[ఀ-౿]", te["text"])
        assert re.search("[ऀ-ॿ]", hi["text"])

    def test_risk_label_is_translated(self):
        te = build_script("te", ROUTE, 3.8, ETA, "High risk", LEGS)["text"]
        assert TEXT["te"]["High risk"] in te

    def test_unknown_language_falls_back_to_english(self):
        script = build_script("xx", ROUTE, 3.8, ETA, "Low risk", LEGS)
        assert script["lang"] == "en"
        assert script["speech_lang"] == "en-IN"

    def test_empty_route_gives_the_no_route_message(self):
        for route in (None, [], ["Only one place"]):
            script = build_script("en", route, 0, None, "", [])
            assert script["sentences"] == [VOICE_TEXT["en"]["no_route"]]

    def test_missing_eta_is_skipped(self):
        text = build_script("en", ROUTE, 3.8, None, "Low risk", LEGS)["text"]
        assert "Estimated time" not in text

    def test_no_route_script_in_each_language(self):
        for lang in LANGS:
            script = no_route_script(lang)
            assert script["text"] == VOICE_TEXT[lang]["no_route"]
            assert script["speech_lang"] == SPEECH_LANG[lang]


class TestFormatting:
    def test_whole_kilometres_have_no_decimals(self):
        assert _km(2.0) == "2"
        assert _km(3.25) == "3.25"
        assert _km(1.8) == "1.8"

    def test_minutes_and_hours(self):
        assert spoken_minutes("en", 12.4) == "12 minutes"
        assert spoken_minutes("en", 0.2) == "1 minutes"     # never "0"
        assert spoken_minutes("en", 75) == "1 hour 15 minutes"
        assert spoken_minutes("en", 135) == "2 hours 15 minutes"
        assert "15" in spoken_minutes("te", 75)
        assert "12" in spoken_minutes("hi", 12)


# =========================================================
# /api/voice
# =========================================================
@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestVoiceEndpoint:
    def test_manual_destination(self, client):
        res = client.get("/api/voice?source=Government+Hospital"
                         "&destination=Evacuation+Center")
        assert res.status_code == 200
        data = res.get_json()
        assert data["ok"] is True
        assert data["speech_lang"] == "en-IN"
        assert data["route"][0] == "Government Hospital"
        assert data["route"][-1] == "Evacuation Center"
        assert "Government Hospital" in data["text"]
        assert len(data["sentences"]) >= 3

    def test_auto_shelter(self, client):
        res = client.get("/api/voice?source=Nandyal+Bus+Stand"
                         "&destination=AUTO&people=3")
        assert res.status_code == 200
        assert res.get_json()["ok"] is True

    def test_language_parameter(self, client):
        for code, speech in (("te", "te-IN"), ("hi", "hi-IN")):
            res = client.get("/api/voice?source=Gandhi+Chowk"
                             f"&destination=AUTO&lang={code}")
            assert res.status_code == 200
            data = res.get_json()
            assert data["lang"] == code
            assert data["speech_lang"] == speech

    def test_unknown_language_uses_english(self, client):
        res = client.get("/api/voice?source=Gandhi+Chowk&lang=zz")
        assert res.get_json()["lang"] == "en"

    def test_missing_source(self, client):
        res = client.get("/api/voice")
        assert res.status_code == 400
        data = res.get_json()
        assert data["ok"] is False
        assert data["sentences"]                  # still has a sentence to speak

    def test_unknown_source(self, client):
        res = client.get("/api/voice?source=Atlantis")
        assert res.status_code == 400

    def test_group_too_big_for_any_shelter(self, client):
        res = client.get("/api/voice?source=Gandhi+Chowk"
                         "&destination=AUTO&people=100000")
        assert res.status_code == 404
        data = res.get_json()
        assert data["ok"] is False
        assert data["text"] == VOICE_TEXT["en"]["no_route"]

    def test_bad_numbers_are_ignored(self, client):
        res = client.get("/api/voice?source=Gandhi+Chowk"
                         "&people=many&surge=lots")
        assert res.status_code == 200

    def test_voice_js_is_served(self, client):
        res = client.get("/static/voice.js")
        assert res.status_code == 200
        assert b"VoiceGuide" in res.data
        res.close()
