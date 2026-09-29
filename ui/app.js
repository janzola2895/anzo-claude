/* ANZO front end: wake word, streaming replies, sentence-by-sentence TTS,
   and interrupt-on-new-speech while a turn is running.

   Recognition runs continuously (Chrome's Web Speech API, free). Chrome
   stops it after a pause even in continuous mode, so onend always
   restarts it unless we deliberately called stop(). */

const TOKEN = window.ANZO_TOKEN;
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");
const convButton = document.getElementById("conv-toggle");

const State = { IDLE: "idle", LISTENING: "listening", WORKING: "working" };
let state = State.IDLE;
let sessionId = null;
let eventSource = null;
let sentenceBuffer = "";
let wantRecognition = true;
// "Modo conversación": once on, ANZO keeps listening without the wake word
// until "pausa" or "cambio y fuera" -- see setConversationMode().
let conversationMode = false;
let convPaused = false;

// The visual orb now lives in orb.js (Three.js) and exposes itself on
// window so this plain script doesn't need to become a module. Guarded in
// case the CDN fails to load: the voice/browser pipeline must keep working
// even if the decorative orb doesn't.
function setOrb(cls) { if (window.setOrbState) window.setOrbState(cls); }
function setStatus(text) { statusEl.textContent = text; }
function logLine(cls, text) {
  const div = document.createElement("div");
  div.className = cls;
  div.textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

// "jarvis" is here because Chrome's Spanish recognizer routinely mishears
// the English pronunciation as "yarvis" -- both are accepted.
const WAKE_WORDS = ["anzo", "yarvis", "jarvis", "viernes"];
const WAKE_WORD_ALT = WAKE_WORDS.join("|");

function stripWakeWord(text) {
  // normalize() maps each character 1:1 (accented -> base letter, same
  // length) so an index found in the normalized string lines up with the
  // same position in the original.
  const re = new RegExp(`(?:hola\\s+)?(?:${WAKE_WORD_ALT})[,:]?\\s*`, "i");
  const m = re.exec(normalize(text));
  if (!m) return null;
  return text.slice(m.index + m[0].length).trim();
}

function normalize(text) {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

function stripMarkdown(text) {
  return text
    .replace(/```[\s\S]*?```/g, "")           // fenced code blocks
    .replace(/`([^`]+)`/g, "$1")              // inline code
    .replace(/\*\*([^*]+)\*\*/g, "$1")        // bold **text**
    .replace(/__([^_]+)__/g, "$1")            // bold __text__
    .replace(/\*([^*]+)\*/g, "$1")            // italic *text*
    .replace(/(?<!\w)_([^_]+)_(?!\w)/g, "$1") // italic _text_
    .replace(/^#{1,6}\s+/gm, "")              // headers
    .replace(/^[-*+]\s+/gm, "")               // bullet markers
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")  // [text](url)
    .replace(/^>\s?/gm, "");                  // blockquote markers
}

let spanishVoice = null;

function pickSpanishVoice() {
  const voices = window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith("es"));
  if (!voices.length) return null;
  // Preference order, all free, no setup required beyond what's already
  // installed: a Windows 11 "Natural" voice (far less robotic than classic
  // SAPI5, but only present if the user added one under Settings > Time &
  // Language > Speech) > Chrome's own cloud "Google" voices (usually
  // decent quality, no installation needed, just requires internet) >
  // any other local voice > whatever's first.
  const natural = voices.find((v) => /natural/i.test(v.name));
  const google = voices.find((v) => /google/i.test(v.name));
  const local = voices.find((v) => v.localService);
  return natural || google || local || voices[0];
}

if (window.speechSynthesis) {
  spanishVoice = pickSpanishVoice();
  window.speechSynthesis.onvoiceschanged = () => { spanishVoice = pickSpanishVoice(); };
}

// Rolling buffer of what Anzo has recently said, so speech recognition
// picking up its own voice through the speakers isn't mistaken for the
// user interrupting. Not real acoustic echo cancellation (the Web Speech
// API doesn't expose the mic constraints needed for that) -- just a
// text-similarity check against what should currently be audible.
let recentlySpoken = "";

// A turn's "complete" event (state -> LISTENING) fires as soon as Claude's
// text is done, but speechSynthesis keeps reading it aloud for several more
// seconds after that -- so the mic can pick up Anzo's own voice well after
// the state machine has already moved past WORKING. inEchoWindow tracks
// actual audio playback (via each utterance's onend), not turn state, so
// looksLikeEcho() stays accurate regardless of which state we're in by the
// time the speakers are still going.
let inEchoWindow = false;
let pendingUtterances = 0;
let echoGraceTimer = null;
const ECHO_GRACE_MS = 1200; // trailing audio / mic lag after the last utterance ends
// Safety net: speechSynthesis's onend/onerror don't always fire (confirmed
// live -- speaking went back to false but neither event followed). Without
// a fallback, one missed event wedges inEchoWindow "true" forever and Anzo
// stops responding to everything, permanently. ~70ms/char is a slow, safe
// reading pace so this fires only once the utterance should clearly be over.
const FALLBACK_MS_PER_CHAR = 70;
const FALLBACK_MIN_MS = 3000;

// normalize() only strips accents/case -- flushSentence() speaks one
// sentence per speak() call, so a short reply is often two or three
// separate utterances back to back, and speech RECOGNITION frequently
// hears them as a single continuous utterance spanning that boundary
// (confirmed live: "...graficos En que te ayudo" heard as one chunk).
// recentlySpoken still has the sentence's punctuation ("graficos. ¿En"),
// so a punctuation-free substring match across that boundary silently
// failed. Stripping punctuation on both sides fixes that.
function normalizeForEcho(text) {
  return normalize(text).replace(/[.,!?¿¡:;"'()\-–—]/g, " ").replace(/\s+/g, " ").trim();
}

function looksLikeEcho(heard) {
  if (!inEchoWindow) return false;
  const n = normalizeForEcho(heard);
  if (n.length < 4) return false; // too short to judge either way
  return recentlySpoken.includes(n);
}

function speak(rawText) {
  const text = stripMarkdown(rawText);
  if (!text.trim() || !window.speechSynthesis) return;
  recentlySpoken = (recentlySpoken + " " + normalizeForEcho(text)).slice(-500);
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "es-CO";
  if (spanishVoice) u.voice = spanishVoice;
  pendingUtterances++;
  inEchoWindow = true;
  clearTimeout(echoGraceTimer);
  let settled = false;
  const onSettle = () => {
    if (settled) return; // onend/onerror and the fallback timer can both fire -- count once
    settled = true;
    pendingUtterances = Math.max(0, pendingUtterances - 1);
    if (pendingUtterances === 0) {
      clearTimeout(echoGraceTimer);
      echoGraceTimer = setTimeout(() => { inEchoWindow = false; }, ECHO_GRACE_MS);
    }
  };
  u.onend = onSettle;
  u.onerror = onSettle;
  setTimeout(onSettle, Math.max(FALLBACK_MIN_MS, text.length * FALLBACK_MS_PER_CHAR));
  window.speechSynthesis.speak(u);
}

function flushSentence(force) {
  const re = /[^.!?\n]+[.!?\n]+/;
  let m;
  while ((m = re.exec(sentenceBuffer))) {
    speak(m[0]);
    sentenceBuffer = sentenceBuffer.slice(m[0].length);
  }
  if (force && sentenceBuffer.trim()) {
    speak(sentenceBuffer);
    sentenceBuffer = "";
  }
}

function interruptCurrentTurn() {
  if (eventSource) { eventSource.close(); eventSource = null; }
  window.speechSynthesis.cancel();
  sentenceBuffer = "";
  fetch("/api/interrupt", { method: "POST", headers: { "X-Anzo-Token": TOKEN } }).catch(() => {});
}

function startTurn(message) {
  if (state === State.WORKING) {
    logLine("sys", "(interrumpido)");
    interruptCurrentTurn();
  }
  clearTimeout(listeningTimeout);
  recentlySpoken = "";
  state = State.WORKING;
  setOrb("working");
  setStatus("Pensando…");
  logLine("you", "Tú: " + message);

  const params = new URLSearchParams({ token: TOKEN, message });
  if (sessionId) params.set("session_id", sessionId);
  eventSource = new EventSource("/api/stream?" + params.toString());
  let replyBuffer = "";

  eventSource.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    switch (ev.t) {
      case "status":
        sessionId = ev.session_id || sessionId;
        logLine("sys", `(modelo: ${ev.model}, herramientas: ${ev.tools}, mcp: [${(ev.mcp || []).join(", ")}])`);
        break;
      case "delta":
        replyBuffer += ev.text;
        sentenceBuffer += ev.text;
        setOrb("speaking");
        flushSentence(false);
        break;
      case "tool":
        if (ev.phase === "use") logLine("sys", "→ " + ev.name);
        break;
      case "warning":
        logLine("sys", "⚠ " + ev.message);
        break;
      case "complete":
        sessionId = ev.session_id || sessionId;
        flushSentence(true);
        if (replyBuffer.trim()) logLine("anzo", "Anzo: " + replyBuffer.trim());
        finishTurn(conversationMode
          ? "Te escucho…"
          : "Puedes responder directamente, o di \"Anzo\" para algo nuevo");
        break;
      case "interrupted":
        finishTurn("Interrumpido. Puedes seguir hablando");
        break;
      case "error":
        logLine("sys", "Error: " + ev.message);
        finishTurn("Hubo un error. Puedes reintentar");
        break;
    }
  };

  eventSource.onerror = () => {
    if (eventSource) { eventSource.close(); eventSource = null; }
    if (state === State.WORKING) finishTurn("Se perdió la conexión. Puedes reintentar");
  };
}

// After a turn ends, keep listening for a follow-up without requiring the
// wake word again for a short window -- answering a question Anzo just
// asked, or a quick correction, shouldn't need "Anzo" every single time.
// Falls back to requiring the wake word again if nothing is said in time.
let listeningTimeout = null;
const FOLLOW_UP_WINDOW_MS = 12000;

function finishTurn(statusText) {
  eventSource = null;
  state = State.LISTENING;
  setOrb("listening");
  setStatus(statusText);
  clearTimeout(listeningTimeout);
  if (conversationMode) return; // stays LISTENING indefinitely -- see setConversationMode()
  listeningTimeout = setTimeout(() => {
    if (state === State.LISTENING) {
      state = State.IDLE;
      setOrb("idle");
      setStatus("Di \"Anzo\" para empezar");
    }
  }, FOLLOW_UP_WINDOW_MS);
}

// Matches a whole utterance (ignoring accents/case/trailing punctuation)
// against one or more control phrases, e.g. isPhrase(text, "pausa").
function isPhrase(text, ...variants) {
  const n = normalize(text).trim().replace(/[.,!?¿¡]+$/, "");
  return variants.includes(n);
}

function updateConvButton() {
  if (!convButton) return;
  convButton.textContent = conversationMode ? "Modo conversación: ON" : "Modo conversación: OFF";
  convButton.setAttribute("aria-pressed", String(conversationMode));
}

// Modo conversación: once activated, the follow-up window (finishTurn,
// above) never expires back to IDLE, so ANZO keeps listening without
// needing the wake word again -- until "cambio y fuera" ends it, or
// "pausa" holds it without ending the session (see setConvPaused).
function setConversationMode(on) {
  conversationMode = on;
  convPaused = false;
  updateConvButton();
  clearTimeout(listeningTimeout);
  if (on) {
    if (state !== State.WORKING) { state = State.LISTENING; setOrb("listening"); }
    setStatus("Modo conversación activo. Di \"pausa\" o \"cambio y fuera\" cuando quieras.");
    speak("Modo conversación activado.");
  } else {
    state = State.IDLE;
    setOrb("idle");
    setStatus("Di \"Anzo\" para empezar");
    speak("Cambio y fuera.");
  }
}

function setConvPaused(on) {
  convPaused = on;
  setStatus(on ? "En pausa. Di \"continúa\" para seguir." : "Te escucho…");
  speak(on ? "En pausa." : "Seguimos.");
}

function toggleConversationModeFromUI() {
  if (state === State.WORKING) return;
  setConversationMode(!conversationMode);
}

function onFinalUtterance(text) {
  if (!text.trim()) return;
  // Checked first, regardless of state: a turn's "complete" event (and the
  // state change that comes with it) fires as soon as the text is done, but
  // speechSynthesis keeps reading it aloud for several seconds afterward --
  // so Anzo's own voice can leak into the mic well after WORKING has ended
  // (this is what "se esta escuchando a si mismo" turned out to be: the
  // echo check used to only run during WORKING and missed that window
  // entirely). Also guards IDLE: a reply that happens to contain a wake
  // word ("viernes" is an ordinary Spanish word) shouldn't wake Anzo up.
  if (looksLikeEcho(text)) return;

  // Paused inside conversation mode: ignore everything except the phrase
  // that wakes it back up (no wake word needed, same as the rest of
  // conversation mode).
  if (conversationMode && convPaused) {
    if (isPhrase(text, "continua", "anzo continua", "sigamos", "sigue")) setConvPaused(false);
    return;
  }

  if (state === State.WORKING) {
    if (conversationMode && isPhrase(text, "pausa")) {
      interruptCurrentTurn();
      finishTurn("En pausa.");
      setConvPaused(true);
      return;
    }
    if (conversationMode && isPhrase(text, "cambio y fuera")) {
      interruptCurrentTurn();
      finishTurn("Cambio y fuera.");
      setConversationMode(false);
      return;
    }
    // Any other speech while a turn is running is an interrupt: stop it
    // and treat this utterance as the new instruction, same session.
    startTurn(text);
    return;
  }

  if (conversationMode) {
    // Behaves like an indefinitely-extended LISTENING state: no wake word
    // needed, and the control phrases are always checked first so they
    // never get sent to Claude as a regular instruction.
    if (isPhrase(text, "cambio y fuera")) { setConversationMode(false); return; }
    if (isPhrase(text, "pausa")) { setConvPaused(true); return; }
    startTurn(text);
    return;
  }

  if (state === State.IDLE) {
    const rest = stripWakeWord(text);
    if (rest === null) return; // no wake word heard, ignore
    if (rest) {
      if (isPhrase(rest, "modo conversacion", "activa modo conversacion")) { setConversationMode(true); return; }
      startTurn(rest);
      return;
    }
    state = State.LISTENING;
    setOrb("listening");
    setStatus("Te escucho…");
    return;
  }

  if (state === State.LISTENING) {
    if (isPhrase(text, "modo conversacion", "activa modo conversacion")) { setConversationMode(true); return; }
    startTurn(text);
    return;
  }
}

function setupRecognition() {
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Ctor) {
    setStatus("Este navegador no soporta reconocimiento de voz. Usa Chrome.");
    return;
  }
  const recognition = new Ctor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "es-CO";

  recognition.onresult = (event) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const result = event.results[i];
      if (result.isFinal) onFinalUtterance(result[0].transcript);
    }
  };

  recognition.onend = () => {
    if (wantRecognition) recognition.start();
  };

  recognition.onerror = (e) => {
    // "no-speech" and "aborted" are routine; anything else is worth a log line.
    if (e.error !== "no-speech" && e.error !== "aborted") {
      logLine("sys", "Reconocimiento: " + e.error);
    }
  };

  recognition.start();
}

window.addEventListener("DOMContentLoaded", () => {
  if (!TOKEN) { setStatus("Falta el token — recarga la página."); return; }
  if (convButton) convButton.addEventListener("click", toggleConversationModeFromUI);
  setupRecognition();
});
