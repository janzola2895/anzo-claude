/* ANZO front end: wake word, streaming replies, sentence-by-sentence TTS,
   and interrupt-on-new-speech while a turn is running.

   Recognition runs continuously (Chrome's Web Speech API, free). Chrome
   stops it after a pause even in continuous mode, so onend always
   restarts it unless we deliberately called stop(). */

const TOKEN = window.ANZO_TOKEN;
const orb = document.getElementById("orb");
const statusEl = document.getElementById("status");
const logEl = document.getElementById("log");

const State = { IDLE: "idle", LISTENING: "listening", WORKING: "working" };
let state = State.IDLE;
let sessionId = null;
let eventSource = null;
let sentenceBuffer = "";
let wantRecognition = true;

function setOrb(cls) { orb.className = cls; }
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
  // Windows 11 "Natural" voices (installed under Settings > Time & Language >
  // Speech) sound far less robotic than the classic SAPI5 ones Chrome
  // defaults to — prefer one if the user has any installed, for free.
  const natural = voices.find((v) => /natural/i.test(v.name));
  const local = voices.find((v) => v.localService);
  return natural || local || voices[0];
}

if (window.speechSynthesis) {
  spanishVoice = pickSpanishVoice();
  window.speechSynthesis.onvoiceschanged = () => { spanishVoice = pickSpanishVoice(); };
}

function speak(rawText) {
  const text = stripMarkdown(rawText);
  if (!text.trim() || !window.speechSynthesis) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "es-CO";
  if (spanishVoice) u.voice = spanishVoice;
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
        finishTurn("Di \"Anzo\" para el siguiente paso");
        break;
      case "interrupted":
        finishTurn("Interrumpido. Di \"Anzo\" para continuar");
        break;
      case "error":
        logLine("sys", "Error: " + ev.message);
        finishTurn("Hubo un error. Di \"Anzo\" para reintentar");
        break;
    }
  };

  eventSource.onerror = () => {
    if (eventSource) { eventSource.close(); eventSource = null; }
    if (state === State.WORKING) finishTurn("Se perdió la conexión. Di \"Anzo\" para reintentar");
  };
}

function finishTurn(statusText) {
  eventSource = null;
  state = State.IDLE;
  setOrb("idle");
  setStatus(statusText);
}

function onFinalUtterance(text) {
  if (!text.trim()) return;

  if (state === State.WORKING) {
    // Any speech while a turn is running is an interrupt: stop it and
    // treat this utterance as the new instruction, same session.
    startTurn(text);
    return;
  }

  if (state === State.IDLE) {
    const rest = stripWakeWord(text);
    if (rest === null) return; // no wake word heard, ignore
    if (rest) { startTurn(rest); return; }
    state = State.LISTENING;
    setOrb("listening");
    setStatus("Te escucho…");
    return;
  }

  if (state === State.LISTENING) {
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
  setupRecognition();
});
