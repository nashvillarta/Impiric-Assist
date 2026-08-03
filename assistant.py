import sys

IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import winsound
import pyautogui
import pyaudio
import json
import time
import os
import subprocess
import requests
import webbrowser
import voice_lines
from vosk import Model, KaldiRecognizer

# --- Global State ---
PLANES_LOCKED = False

# --- Voice Pack (pre-rendered audio, see tools/generate_voice_pack.py) ---
VOICE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice")


def _play_wav(path, stream=None):
    """Plays a WAV, pausing the mic so the assistant does not hear itself.

    Returns True if it played. Blocking on purpose: speech must finish before
    confirm_action starts listening.
    """
    if not os.path.exists(path):
        return False
    try:
        if stream is not None:
            stream.stop_stream()
        try:
            if IS_WINDOWS:
                winsound.PlaySound(path, winsound.SND_FILENAME)
            else:
                subprocess.run(["afplay", path])
        finally:
            if stream is not None:
                stream.start_stream()
        return True
    except Exception as e:
        print(f"[Voice Warning] Could not play {os.path.basename(path)}: {e}")
        return False


def _speak_native(text):
    """Platform TTS. Only reached when the voice pack has no line for this text."""
    try:
        if IS_WINDOWS:
            # Text goes in over stdin, never interpolated into the command line:
            # it can carry an LLM-supplied amount, and os.system would make that
            # a shell injection (stripping ' does not stop " or ; or $(...)).
            script = (
                "Add-Type -AssemblyName System.Speech; "
                "(New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak([Console]::In.ReadToEnd())"
            )
            subprocess.run(["powershell", "-Command", script], input=text, text=True)
        else:
            subprocess.run(["say", text])
    except Exception as e:
        print(f"[TTS Warning] Could not initialize voice engine: {e}")


# --- AI Voice (Text-to-Speech) Setup ---
def speak(text, stream=None):
    """Prints text and speaks it, preferring the pre-rendered voice pack."""
    print(f"\n[AI Voice]: \"{text}\"")
    if _play_wav(os.path.join(VOICE_DIR, voice_lines.slug(text) + ".wav"), stream):
        return
    _speak_native(text)


# --- Confirmation Listener ---
def confirm_action(action_description, stream, recognizer, timeout_seconds=5):
    """Asks the user for confirmation and listens for a Yes/No answer (Reads partials for 0ms latency)."""
    speak(f"Confirm: {action_description}?", stream)
    print(f"\n[CONFIRMATION REQUIRED] Say 'Yes' to execute or 'No' to cancel... (Listening for {timeout_seconds}s)")
    
    start_time = time.time()
    while time.time() - start_time < timeout_seconds:
        data = stream.read(4000, exception_on_overflow=False)
        
        # Check both Final and Partial results simultaneously
        is_final = recognizer.AcceptWaveform(data)
        
        if is_final:
            result = json.loads(recognizer.Result())
            text = result.get("text", "").lower()
        else:
            result = json.loads(recognizer.PartialResult())
            text = result.get("partial", "").lower()

        if text:
            if is_final:
                print(f"Confirmation response heard: \"{text}\"")
            else:
                sys.stdout.write(f"\rListening for confirmation... [ {text} ]")
                sys.stdout.flush()

            # The second it sees these words, it triggers. No waiting for silence!
            if any(w in text for w in ["yes", "yeah", "yup", "confirm", "do it", "ok", "okay", "sure", "ya", "aye"]):
                print(f"\nConfirmation response caught: \"{text}\"")
                speak("Okay.", stream)
                return True
            elif any(w in text for w in ["no", "nope", "cancel", "stop", "dont", "don't", "nah"]):
                print(f"\nConfirmation response caught: \"{text}\"")
                speak("Command cancelled.", stream)
                return False

    print("\n[CONFIRMATION TIMEOUT] No confirmation received.")
    speak("Timed out. Action cancelled.", stream)
    return False

# --- Number Parsing Helper ---
def parse_number(text):
    number_words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "too": 2}  # "to"/"for" deliberately excluded: too ambiguous, they show up in normal command phrases
    for word in text.split():
        if word.isdigit():
             return int(word)
        if word in number_words:
             return number_words[word]
    return 1

# --- Reliable Hotkey Sender ---
# Note: pyautogui maps 'alt' to Option and 'ctrl' to Control on macOS, so these Ctrl+Shift+Alt combos already translate.
def send_shortcut(target_key):
    """Holds modifiers, presses the key, and releases."""
    pyautogui.keyDown('ctrl')
    pyautogui.keyDown('shift')
    pyautogui.keyDown('alt')
    time.sleep(0.05) 
    
    pyautogui.keyDown(target_key)
    time.sleep(0.05) 
    pyautogui.keyUp(target_key)
    
    pyautogui.keyUp('alt')
    pyautogui.keyUp('shift')
    pyautogui.keyUp('ctrl')

# --- Core SpaceWalker Commands ---
def trigger_action(name, key, amount=1):
    """Holds modifiers ONCE and taps the action key multiple times to avoid Sticky Keys."""
    if amount > 1:
        print(f"\n[ACTION] {name} ({amount} times) -> Ctrl+Shift+Alt+{key.upper()}")
    else:
        print(f"\n[ACTION] {name} -> Ctrl+Shift+Alt+{key.upper()}")
        
    pyautogui.keyDown('ctrl')
    pyautogui.keyDown('shift')
    pyautogui.keyDown('alt')
    time.sleep(0.05)
    
    for _ in range(amount):
        pyautogui.keyDown(key)
        time.sleep(0.05)
        pyautogui.keyUp(key)
        time.sleep(0.1)
        
    pyautogui.keyUp('alt')
    pyautogui.keyUp('shift')
    pyautogui.keyUp('ctrl')

def trigger_clear_screens():
    """Triggered by 'B One' to minimize windows and clear screens."""
    if not IS_WINDOWS:
        print("\n[ACTION] B One -> Clear screens is Windows-only (SpaceWalker); skipping.")
        return
    print("\n[ACTION] B One -> Clearing screens (Win+D)...")
    pyautogui.hotkey('win', 'd')

def trigger_toggle_planes():
    """Triggered by 'A One' to lock/unlock all 3 orientation planes (X, Y, Z)."""
    global PLANES_LOCKED
    PLANES_LOCKED = not PLANES_LOCKED
    
    if PLANES_LOCKED:
        print("\n[ACTION] A One -> Locking planes (Screens will now follow your gaze)...")
    else:
        print("\n[ACTION] A One -> Unlocking planes (Screens are now pinned in space)...")

    pyautogui.keyDown('ctrl')
    pyautogui.keyDown('shift')
    pyautogui.keyDown('alt')
    time.sleep(0.05)

    for key in ['x', 'y', 'z']:
        pyautogui.keyDown(key)
        time.sleep(0.05)
        pyautogui.keyUp(key)
        time.sleep(0.05)

    pyautogui.keyUp('alt')
    pyautogui.keyUp('shift')
    pyautogui.keyUp('ctrl')

# --- LLM Brain (Ollama) ---
def query_ollama(command_text):
    """Sends complex natural language queries to Ollama when fast-path rules don't catch it."""
    url = "http://127.0.0.1:11434/api/generate"
    
    system_prompt = """You are a smart controller for a user's virtual AR monitors. 
Read the user's input and map their intent to ONE of the following actions:
- 'recenter' (if they want to fix, center, or align their screens)
- 'push' (if they want to move screens further away, push, or bush)
- 'pull' (if they want to bring screens closer, pull, or near)
- 'clear' (if they say B One, clear, or hide screens)
- 'lock_planes' (if they say A One, lock planes, or lock tilt)
- 'open_gemini' (if they ask to open Gemini, chat with Gemini, or start AI)
- 'layout_ultrawide' (0)
- 'layout_single' (1)
- 'layout_dual' (2)
- 'layout_triple' (3)
- 'layout_stacked' (7)
- 'unknown'

If the action is 'push' or 'pull', extract the amount (default is 1).
You MUST respond ONLY in valid JSON format. Example: {"action": "push", "amount": 3}"""

    payload = {
        "model": "phi3",
        "prompt": f"{system_prompt}\n\nUser Input: {command_text}",
        "stream": False,
        "format": "json"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return json.loads(response.json()['response'])
    except Exception as e:
        print(f"\n[Ollama Error] Could not reach the LLM: {e}")
        return {"action": "unknown", "amount": 1}

def process_and_execute(phrase, stream, recognizer):
    """Checks fast-path keyword matches first, then falls back to Ollama LLM, requiring confirmation before execution."""
    
    # 1. "A One" -> Toggle orientation planes
    if any(word in phrase for word in ["a one", "a 1", "a1", "ae one", "ay one", "a wine"]):
        state_str = "Lock" if not PLANES_LOCKED else "Unlock"
        if confirm_action(f"{state_str} orientation planes", stream, recognizer):
            trigger_toggle_planes()
        return

    # 2. "B One" -> Clear Screens (Win+D)
    if any(word in phrase for word in ["b one", "b 1", "b1", "be one", "bee one"]):
        if confirm_action("Clear screens", stream, recognizer):
            trigger_clear_screens()
        return

    # 3. Quick Recenter
    if any(word in phrase for word in ["re center", "recenter", "center", "fix", "reseller", "read center", "resented"]):
        if confirm_action("Recenter displays", stream, recognizer):
            print("\n[ACTION] Recenter -> Ctrl+Shift+Alt+R")
            send_shortcut('r')
        return

    # 4. Quick Push
    if any(word in phrase for word in ["push", "bush", "put", "away", "further"]):
        amount = parse_number(phrase)
        if confirm_action(f"Push displays away by {amount}", stream, recognizer):
            trigger_action("Push", 'down', amount)
        return

    # 5. Quick Pull
    if any(word in phrase for word in ["pull", "pool", "pole", "closer", "near", "all by", "oh by", "poll", "paul", "cool"]):
        amount = parse_number(phrase)
        if confirm_action(f"Pull displays closer by {amount}", stream, recognizer):
            trigger_action("Pull", 'up', amount)
        return

    # 6. Open Gemini
    if any(word in phrase for word in ["open gemini", "chat with gemini", "gemini live", "talk to gemini", "start gemini"]):
        if confirm_action("Open Gemini", stream, recognizer):
            print("\n[ACTION] Opening Gemini...")
            webbrowser.open("https://gemini.google.com/")
        return

    # --- LLM FALLBACK ---
    print("Thinking (LLM)...")
    intent_data = query_ollama(phrase)
    action = intent_data.get("action", "unknown")
    # The LLM can return anything here, so clamp it to a sane int before it
    # reaches a spoken string or range(). Also keeps it inside the voiced range.
    try:
        amount = max(1, min(int(intent_data.get("amount", 1)), voice_lines.MAX_AMOUNT))
    except (TypeError, ValueError):
        amount = 1
    
    if action == "recenter":
        if confirm_action("Recenter displays", stream, recognizer):
            send_shortcut('r')
    elif action == "push":
        if confirm_action(f"Push displays away by {amount}", stream, recognizer):
            trigger_action("Push", 'down', amount)
    elif action == "pull":
        if confirm_action(f"Pull displays closer by {amount}", stream, recognizer):
            trigger_action("Pull", 'up', amount)
    elif action == "clear":
        if confirm_action("Clear screens", stream, recognizer):
            trigger_clear_screens()
    elif action == "lock_planes":
        state_str = "Lock" if not PLANES_LOCKED else "Unlock"
        if confirm_action(f"{state_str} orientation planes", stream, recognizer):
            trigger_toggle_planes()
    elif action == "open_gemini":
        if confirm_action("Open Gemini", stream, recognizer):
            print("\n[ACTION] Opening Gemini...")
            webbrowser.open("https://gemini.google.com/")
    elif action == "layout_ultrawide":
        if confirm_action("Switch to Ultrawide layout", stream, recognizer):
            send_shortcut('0')
    elif action == "layout_single":
        if confirm_action("Switch to Single display layout", stream, recognizer):
            send_shortcut('1')
    elif action == "layout_dual":
        if confirm_action("Switch to Dual display layout", stream, recognizer):
            send_shortcut('2')
    elif action == "layout_triple":
        if confirm_action("Switch to Triple display layout", stream, recognizer):
            send_shortcut('3')
    elif action == "layout_stacked":
        if confirm_action("Switch to Stacked display layout", stream, recognizer):
            send_shortcut('7')
    else:
        print(f"\n[ACTION] Unknown intent.")
        speak("Sorry, I did not understand that.", stream)

def main():
    if not os.path.exists("model"):
        print("[ERROR] Could not find the 'model' folder for Vosk.")
        return

    print("\nLoading Vosk Ear Model...")
    model = Model("model")
    recognizer = KaldiRecognizer(model, 16000)

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=8000)
    stream.start_stream()

    print("\n==================================================")
    print("  SAFE SMART AI ASSISTANT (Confirmation Required)")
    print("  - 'Computer B One' : Clear screens (Requires 'Yes')")
    print("  - 'Computer A One' : Lock/Unlock orientation")
    print("  - 'Computer Open Gemini' : Launches Gemini Web Chat")
    print("==================================================")

    if not IS_WINDOWS:
        print("[macOS] Grant Terminal Accessibility permission (System Settings > Privacy & Security > Accessibility) so keystrokes reach other apps. Note: 'B One' (clear screens) is Windows-only.")

    speak("Assistant ready.", stream)
    print("\nReady! Listening...\n")

    listening_for_command = False

    while True:
        data = stream.read(4000, exception_on_overflow=False)
        
        if recognizer.AcceptWaveform(data):
            result = json.loads(recognizer.Result())
            phrase = result.get("text", "").lower()
            
            if phrase:
                sys.stdout.write('\r' + ' ' * 60 + '\r')
                sys.stdout.flush()
                
                print(f"Heard: \"{phrase}\"")

                if listening_for_command:
                    process_and_execute(phrase, stream, recognizer)
                    listening_for_command = False
                
                elif "computer" in phrase:
                    command_part = phrase.split("computer", 1)[-1].strip()
                    
                    if command_part: 
                        process_and_execute(command_part, stream, recognizer)
                    else:
                        speak("Listening.", stream)
                        print("--> Wake word acknowledged! Listening for command...")
                        listening_for_command = True

        else:
            partial_result = json.loads(recognizer.PartialResult())
            partial_text = partial_result.get("partial", "")
            if partial_text:
                sys.stdout.write(f"\rListening... [ {partial_text} ]")
                sys.stdout.flush()

if __name__ == "__main__":
    main()
