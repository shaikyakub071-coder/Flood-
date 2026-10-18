/*
 * voice.js - voice guidance (text-to-speech) and voice input
 * (speech-to-text) for the Flood Evacuation Route Planner.
 *
 * Uses the browser's Web Speech API, so it needs no extra libraries:
 *   - Reading aloud works in Chrome, Edge, Safari and Firefox. The
 *     language needs a voice installed on the device (English, Telugu
 *     and Hindi are standard on Android and most Windows/macOS setups).
 *   - Voice input works in Chrome and Edge (and needs internet).
 *
 * Needs these elements on the page (see voice_snippet.html):
 *   #voice-box      container, data-lang="en|te|hi" and data-msg-* texts
 *   #voice-speak    button: read the route aloud
 *   #voice-listen   button: say your start place / destination
 *   #voice-stop     button: stop talking
 *   #voice-status   text line for messages
 * and the existing form fields named: source, destination, people, surge.
 *
 * Optional:
 *   window.VOICE_ALIASES = { "Kundu River Bank": ["కుందూ నది", "कुंदु नदी"] }
 *   lets people say place names in Telugu or Hindi.
 *   data-auto-submit="1" on #voice-box submits the form after listening.
 */
(function () {
  "use strict";

  var SPEECH_LANG = { en: "en-IN", te: "te-IN", hi: "hi-IN" };
  var AUTO_WORDS = /\s(nearest|auto|automatic|any shelter|safe shelter|సమీప|निकटतम|नज़दीकी)\s/;

  var synth = window.speechSynthesis || null;
  var Recognition =
    window.SpeechRecognition || window.webkitSpeechRecognition || null;
  var box = null;
  var statusEl = null;
  var runId = 0;
  var recognizer = null;

  // ---------------------------------------------------------------- helpers
  function msg(key, fallback) {
    return (box && box.dataset[key]) || fallback;
  }

  function setStatus(text, isError) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.style.color = isError ? "#b00020" : "";
  }

  function field(name) {
    return document.querySelector("[name='" + name + "']");
  }

  function pageLang() {
    var code = (box && box.dataset.lang) || document.documentElement.lang || "en";
    code = String(code).slice(0, 2).toLowerCase();
    return SPEECH_LANG[code] ? code : "en";
  }

  // ---------------------------------------------------------- speaking
  function getVoices() {
    return new Promise(function (resolve) {
      var list = synth.getVoices();
      if (list.length) return resolve(list);
      var done = false;
      function finish() {
        if (done) return;
        done = true;
        resolve(synth.getVoices());
      }
      synth.addEventListener("voiceschanged", finish, { once: true });
      setTimeout(finish, 1000);   // some browsers never fire the event
    });
  }

  function pickVoice(voices, lang) {
    var wanted = lang.toLowerCase();
    var prefix = wanted.split("-")[0];
    var partial = null;
    for (var i = 0; i < voices.length; i++) {
      var code = (voices[i].lang || "").toLowerCase().replace("_", "-");
      if (code === wanted) return voices[i];
      if (!partial && code.split("-")[0] === prefix) partial = voices[i];
    }
    return partial;
  }

  function stop() {
    runId++;
    if (synth) synth.cancel();
    if (recognizer) {
      try { recognizer.abort(); } catch (e) { /* already stopped */ }
    }
  }

  function speakAll(sentences, lang) {
    if (!synth) {
      setStatus(msg("msgUnsupported", "Voice is not supported in this browser."), true);
      return Promise.resolve();
    }
    var myRun = ++runId;
    synth.cancel();
    return getVoices().then(function (voices) {
      var voice = pickVoice(voices, lang);
      if (!voice && lang.indexOf("en") !== 0) {
        setStatus(msg("msgNoVoice",
          "No voice for this language is installed on your device."), true);
      }
      var i = 0;
      function next() {
        if (myRun !== runId || i >= sentences.length) return;
        var u = new SpeechSynthesisUtterance(sentences[i++]);
        u.lang = lang;
        if (voice) u.voice = voice;
        u.rate = 0.9;               // slightly slower = clearer in an emergency
        u.onend = next;
        u.onerror = next;
        synth.speak(u);
      }
      next();
    });
  }

  function speakRoute() {
    var source = field("source");
    if (!source || !source.value) {
      setStatus(msg("msgPickStart", "Select a starting location first."), true);
      return;
    }
    var dest = field("destination");
    var people = field("people");
    var surge = field("surge");
    var params = new URLSearchParams({
      source: source.value,
      destination: (dest && dest.value) || "AUTO",
      people: (people && people.value) || "1",
      surge: (surge && surge.value) || "0"
    });
    if (box && box.dataset.lang) params.set("lang", box.dataset.lang);

    setStatus(msg("msgLoading", "Loading route..."));
    var url = (box && box.dataset.url) || "/api/voice";
    fetch(url + "?" + params.toString(), { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        setStatus("");
        if (data && data.sentences) {
          // also works for "no safe route": the server sends that sentence too
          return speakAll(data.sentences, data.speech_lang || "en-IN");
        }
        setStatus((data && data.error) || "Error", true);
      })
      .catch(function () {
        setStatus(msg("msgOffline", "Could not reach the server."), true);
      });
  }

  // ---------------------------------------------------------- listening
  function norm(text) {
    // keep letters, combining marks (Telugu/Hindi vowel signs) and digits
    return " " + String(text).toLowerCase()
      .replace(/[^\p{L}\p{M}\p{N}\s]/gu, " ")
      .replace(/\s+/g, " ").trim() + " ";
  }

  function optionNames(select) {
    var names = [];
    if (!select) return names;
    for (var i = 0; i < select.options.length; i++) {
      var v = select.options[i].value;
      if (v && v !== "AUTO") names.push(v);
    }
    return names;
  }

  function findPlaces(text) {
    var all = {};
    optionNames(field("source")).concat(optionNames(field("destination")))
      .forEach(function (n) { all[n] = true; });
    var aliases = window.VOICE_ALIASES || {};
    var found = [];

    Object.keys(all).forEach(function (name) {
      var candidates = [name].concat(aliases[name] || []);
      var best = -1;
      candidates.forEach(function (c) {
        var idx = text.indexOf(norm(c));
        if (idx >= 0 && (best < 0 || idx < best)) best = idx;
      });

      if (best < 0) {   // fuzzy: most of the words of the name were heard
        var tokens = norm(name).trim().split(" ").filter(function (w) { return w.length > 2; });
        var hits = 0, first = -1;
        tokens.forEach(function (w) {
          var at = text.indexOf(" " + w + " ");
          if (at >= 0) { hits++; if (first < 0 || at < first) first = at; }
        });
        if (tokens.length && hits / tokens.length >= 0.6) best = first;
      }
      if (best >= 0) found.push({ name: name, idx: best });
    });

    found.sort(function (a, b) { return a.idx - b.idx; });
    return found.map(function (f) { return f.name; });
  }

  function setField(el, value) {
    if (!el) return false;
    el.value = value;
    if (el.value !== value) return false;     // no such option in the list
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return true;
  }

  function applyTranscript(raw) {
    var text = norm(raw);
    var places = findPlaces(text);
    var dst = field("destination");
    var shelters = optionNames(dst);
    var source = null, dest = null;

    if (places.length >= 2) {
      source = places[0];
      dest = places[1];
      // "to the Evacuation Center from Kundu River Bank": swap
      if (shelters.indexOf(source) >= 0 && shelters.indexOf(dest) < 0) {
        var tmp = source; source = dest; dest = tmp;
      }
    } else if (places.length === 1) {
      source = places[0];
    }
    if (!dest && AUTO_WORDS.test(text)) dest = "AUTO";
    if (!source) return null;

    setField(field("source"), source);
    if (dest) setField(dst, dest);

    var count = text.match(/\s(\d{1,4})\s/);
    if (count) setField(field("people"), count[1]);
    return { source: source, destination: dest };
  }

  function listen() {
    if (!Recognition) {
      setStatus(msg("msgNoListen", "Voice input needs Chrome or Edge."), true);
      return;
    }
    if (recognizer) {
      try { recognizer.abort(); } catch (e) { /* ignore */ }
    }
    var rec = new Recognition();
    recognizer = rec;
    rec.lang = SPEECH_LANG[pageLang()];
    rec.interimResults = false;
    rec.maxAlternatives = 3;

    rec.onstart = function () {
      setStatus(msg("msgListening", "Listening..."));
    };
    rec.onresult = function (event) {
      var result = event.results[0];
      var heard = null;
      for (var i = 0; i < result.length && !heard; i++) {
        heard = applyTranscript(result[i].transcript);
      }
      if (!heard) {
        setStatus(msg("msgNotFound", "Could not match a place. Try again.") +
                  " (" + result[0].transcript + ")", true);
        return;
      }
      setStatus(msg("msgHeard", "Heard") + ": " + heard.source +
                (heard.destination ? " → " + heard.destination : ""));
      var src = field("source");
      if (box && box.dataset.autoSubmit === "1" && src && src.form) {
        if (src.form.requestSubmit) src.form.requestSubmit();
        else src.form.submit();
      }
    };
    rec.onerror = function (event) {
      var denied = event.error === "not-allowed" || event.error === "service-not-allowed";
      setStatus(denied
        ? msg("msgMicDenied", "Microphone permission was denied.")
        : msg("msgNotFound", "Could not match a place. Try again."), true);
    };
    rec.onend = function () {
      if (recognizer === rec) recognizer = null;
    };
    rec.start();
  }

  // -------------------------------------------------------------- start up
  function init() {
    box = document.getElementById("voice-box");
    if (!box) return;
    statusEl = document.getElementById("voice-status");

    var speakBtn = document.getElementById("voice-speak");
    var listenBtn = document.getElementById("voice-listen");
    var stopBtn = document.getElementById("voice-stop");

    if (speakBtn) speakBtn.addEventListener("click", speakRoute);
    if (listenBtn) listenBtn.addEventListener("click", listen);
    if (stopBtn) stopBtn.addEventListener("click", stop);

    if (!synth) {
      if (speakBtn) speakBtn.hidden = true;
      if (stopBtn) stopBtn.hidden = true;
    }
    if (!Recognition && listenBtn) listenBtn.hidden = true;
    if (!synth && !Recognition) {
      setStatus(msg("msgUnsupported", "Voice is not supported in this browser."), true);
    }
  }

  window.VoiceGuide = {
    speakRoute: speakRoute,
    listen: listen,
    stop: stop,
    // for alerts, e.g. VoiceGuide.speakText("Road closed", "en-IN")
    speakText: function (text, lang) { return speakAll([text], lang || "en-IN"); }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
