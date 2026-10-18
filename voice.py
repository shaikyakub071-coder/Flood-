"""
voice.py - builds the sentences that are read aloud for a route.

The browser does the actual speaking (Web Speech API). This module only
decides WHAT is said, in English, Telugu or Hindi, so the wording is
tested in Python and the same text can be used by the API, the page or
an SMS later.

    build_script("te", route, distance_km, eta, risk_label, legs)
    -> {"lang": "te", "speech_lang": "te-IN", "text": "...",
        "sentences": ["...", "..."]}
"""

from translations import LANGS, translate

# Language codes the browser's speech engine understands.
SPEECH_LANG = {"en": "en-IN", "te": "te-IN", "hi": "hi-IN"}

VOICE_TEXT = {
    "en": {
        "intro": "Evacuation route from {start} to {dest}. "
                 "Total distance {km} kilometres. Risk level: {risk}.",
        "step": "Go from {a} to {b}, {km} kilometres.",
        "caution": "Caution. This road has {level} flooding.",
        "eta": "Estimated time: {car} by car, {walk} on foot.",
        "arrive": "You will arrive at {dest}. Stay safe.",
        "no_route": "No safe route was found. Please contact the "
                    "emergency control room.",
        "minutes": "{n} minutes",
        "hour_one": "{h} hour {m} minutes",
        "hours": "{h} hours {m} minutes",
    },
    "te": {
        "intro": "{start} నుండి {dest} కు తరలింపు మార్గం. "
                 "మొత్తం దూరం {km} కిలోమీటర్లు. ప్రమాద స్థాయి: {risk}.",
        "step": "{a} నుండి {b} కు వెళ్ళండి, {km} కిలోమీటర్లు.",
        "caution": "జాగ్రత్త. ఈ రోడ్డులో వరద స్థాయి {level}.",
        "eta": "అంచనా సమయం: కారులో {car}, నడకలో {walk}.",
        "arrive": "మీరు {dest} చేరుకుంటారు. జాగ్రత్తగా ఉండండి.",
        "no_route": "సురక్షిత మార్గం దొరకలేదు. దయచేసి అత్యవసర "
                    "నియంత్రణ గదిని సంప్రదించండి.",
        "minutes": "{n} నిమిషాలు",
        "hour_one": "{h} గంట {m} నిమిషాలు",
        "hours": "{h} గంటలు {m} నిమిషాలు",
    },
    "hi": {
        "intro": "{start} से {dest} तक निकासी मार्ग। "
                 "कुल दूरी {km} किलोमीटर। जोखिम स्तर: {risk}।",
        "step": "{a} से {b} तक जाएँ, {km} किलोमीटर।",
        "caution": "सावधान। इस सड़क पर बाढ़ का स्तर {level} है।",
        "eta": "अनुमानित समय: कार से {car}, पैदल {walk}।",
        "arrive": "आप {dest} पहुँचेंगे। सुरक्षित रहें।",
        "no_route": "कोई सुरक्षित मार्ग नहीं मिला। कृपया आपातकालीन "
                    "नियंत्रण कक्ष से संपर्क करें।",
        "minutes": "{n} मिनट",
        "hour_one": "{h} घंटा {m} मिनट",
        "hours": "{h} घंटे {m} मिनट",
    },
}


def _say(lang, key, **values):
    words = VOICE_TEXT.get(lang) or VOICE_TEXT["en"]
    return words.get(key, VOICE_TEXT["en"][key]).format(**values)


def spoken_minutes(lang, minutes):
    """Minutes as a speakable phrase, e.g. '12 minutes'."""
    total = max(int(round(minutes)), 1)
    if total >= 60:
        key = "hour_one" if total < 120 else "hours"
        return _say(lang, key, h=total // 60, m=total % 60)
    return _say(lang, "minutes", n=total)


def _km(value):
    """2.0 -> '2', 3.25 -> '3.25' (speech engines read '2.0' awkwardly)."""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def no_route_script(lang="en"):
    lang = lang if lang in LANGS else "en"
    text = _say(lang, "no_route")
    return {"lang": lang, "speech_lang": SPEECH_LANG[lang],
            "text": text, "sentences": [text]}


def build_script(lang, route, distance_km, eta, risk_label, legs):
    """Sentences to read aloud for one route.

    route        list of place names
    distance_km  total km
    eta          dict from RoadNetwork.route_eta (needs 'car' and 'walk')
    risk_label   English label from RoadNetwork.risk_label
    legs         list from app.route_edges (distance + risk per road)
    """
    lang = lang if lang in LANGS else "en"
    if not route or len(route) < 2:
        return no_route_script(lang)

    sentences = [_say(lang, "intro", start=route[0], dest=route[-1],
                      km=_km(distance_km),
                      risk=translate(lang, risk_label))]

    for leg in legs:
        sentences.append(_say(lang, "step", a=leg["from"], b=leg["to"],
                              km=_km(leg["distance"])))
        # risk is the penalty: 10 = medium flood, 50 = high flood
        if leg["risk"] >= 50:
            sentences.append(_say(lang, "caution",
                                  level=translate(lang, "high")))
        elif leg["risk"] >= 10:
            sentences.append(_say(lang, "caution",
                                  level=translate(lang, "medium")))

    if eta:
        sentences.append(_say(lang, "eta",
                              car=spoken_minutes(lang, eta["car"]),
                              walk=spoken_minutes(lang, eta["walk"])))
    sentences.append(_say(lang, "arrive", dest=route[-1]))

    return {"lang": lang, "speech_lang": SPEECH_LANG[lang],
            "text": " ".join(sentences), "sentences": sentences}
