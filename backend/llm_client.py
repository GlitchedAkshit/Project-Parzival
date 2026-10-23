"""
Talks to a locally-running Ollama server (https://ollama.com) for
open-ended conversation. Fully offline once a model is pulled - no cloud
API, no internet required, no API key.

Setup (one-time, outside this project):
    1. Install Ollama from https://ollama.com
    2. Run: ollama pull llama3.2   (or any other local model you prefer)
    3. Ollama runs a local server automatically on http://localhost:11434

Replies are STREAMED: chat_stream() yields text as the model generates it,
so Parzival can start speaking the first sentence while the rest is still
being written, instead of waiting in silence for the whole answer.
"""

import json

import requests

import config

PARZIVAL_SYSTEM_PROMPT = """You are Parzival, a local, fully offline voice \
assistant running on the user's own PC. You are named after the knight from \
Arthurian legend who quested for the Holy Grail - lean into a calm, \
slightly formal, dryly witty tone, like a knight who has seen everything \
and is unbothered by it. You are not a corporate assistant and you do not \
need to over-explain yourself or add disclaimers. Keep replies SHORT - 1 to \
3 sentences - since they will be read aloud by text-to-speech, not \
displayed as long text. Never say you are an AI language model; you are \
simply Parzival.

The user talks to you by voice through offline speech recognition, so \
their words may contain small transcription mistakes - infer what they \
meant. Besides conversation, your built-in commands can control the \
smart-home devices (lights, fan, thermostat, front door lock), the TV \
(power, volume, mute, pause, channels, and opening YouTube, Netflix, Prime \
Video or Spotify on it), set \
reminders and keep a task list, take a screenshot, lock the PC, change or \
mute the volume, open apps (browser, File Explorer, Notepad, Calculator, \
Task Manager, Windows Settings), play/pause/skip music, and tell the time \
or date. Those commands are handled before a message ever reaches you, so \
if the user asks you to do one, you have NOT done it - tell them the \
phrasing to use instead, e.g. "remind me to stretch in 20 minutes", \
"open YouTube on the TV" or "add milk to my tasks". You cannot browse the internet or read files, so \
never claim to have done those things. Never wrap your reply in quotation \
marks and don't use markdown, lists or emoji."""


class LLMError(Exception):
    """Raised with a short, speakable explanation of what went wrong."""


def fast_local_url(url):
    """'localhost' makes Windows try IPv6 (::1) first; Ollama only listens
    on IPv4, so every request paid a ~2s failed-connection penalty."""
    return url.replace("://localhost", "://127.0.0.1")


def clean_reply(text):
    """Small local models like to wrap the whole reply in quotes."""
    text = text.strip()
    if len(text) >= 2 and text[0] in "\"“" and text[-1] in "\"”":
        text = text[1:-1].strip()
    return text


class OllamaClient:
    def __init__(self, model=None, url=None):
        self.model = model or config.OLLAMA_MODEL
        self.url = fast_local_url(url or config.OLLAMA_URL)
        self.status = "checking"   # checking / ready / offline / missing-model

    def is_available(self):
        try:
            requests.get(self.url.rsplit("/api/", 1)[0], timeout=2)
            return True
        except Exception:
            return False

    def warm_up(self):
        """Loads the model into memory in the background at startup, so the
        first question doesn't wait for a cold model load. Sets .status."""
        try:
            r = requests.post(
                self.url,
                json={"model": self.model, "messages": [], "keep_alive": config.OLLAMA_KEEP_ALIVE},
                timeout=(3, 120),
            )
            self.status = "missing-model" if r.status_code == 404 else "ready" if r.ok else "offline"
        except requests.exceptions.RequestException:
            self.status = "offline"
        return self.status

    def chat_stream(self, history, cancel_event=None):
        """
        history: list of {"role": "user"/"assistant", "content": str}
        Yields Parzival's reply in pieces as it's generated. Raises
        LLMError (with a speakable message) if Ollama can't be reached.
        """
        messages = [{"role": "system", "content": PARZIVAL_SYSTEM_PROMPT}] + history
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
        }

        try:
            with requests.post(self.url, json=payload, stream=True,
                               timeout=(3, config.OLLAMA_TIMEOUT)) as response:
                if response.status_code == 404:
                    self.status = "missing-model"
                    raise LLMError(f"I don't have the {self.model} model yet. "
                                   f"Run ollama pull {self.model} and ask me again.")
                response.raise_for_status()
                self.status = "ready"

                for line in response.iter_lines():
                    if cancel_event is not None and cancel_event.is_set():
                        return
                    if not line:
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise LLMError("My thinking engine reported an error.")
                    piece = data.get("message", {}).get("content", "")
                    if piece:
                        yield piece
                    if data.get("done"):
                        return
        except LLMError:
            raise
        except requests.exceptions.ConnectionError:
            self.status = "offline"
            raise LLMError("I can't reach my thinking engine - is Ollama running?")
        except requests.exceptions.Timeout:
            raise LLMError("My thinking engine took too long to answer.")
        except Exception as e:
            print(f"[llm_client] Ollama request failed: {e}")
            raise LLMError("Something went wrong reaching my thinking engine.")

    def chat(self, history):
        """Non-streaming convenience wrapper (returns the whole reply)."""
        try:
            return clean_reply("".join(self.chat_stream(history)))
        except LLMError as e:
            return str(e)
