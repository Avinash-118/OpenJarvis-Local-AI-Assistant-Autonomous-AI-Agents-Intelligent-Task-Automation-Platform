"""Wake-word gating, bounded capture, and local-agent routing regressions."""

import io
import json
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import jarvis_background as voice


class WakeWordTests(unittest.TestCase):
    def test_background_speech_cannot_start_a_turn(self):
        dialogue = voice.Dialogue()
        self.assertIsNone(dialogue.accept("open gmail", 100, woke=True))
        self.assertIsNone(dialogue.accept("open gmail", 100))

    def test_greeting_does_not_open_an_ambient_conversation_window(self):
        dialogue = voice.Dialogue()
        self.assertEqual(dialogue.accept("Hello Jarvis.", 100, woke=True), "")
        self.assertIsNone(dialogue.accept("what time is it?", 100.1))
        self.assertIsNone(dialogue.accept("tell me more", 159))
        self.assertIsNone(dialogue.accept("open gmail", 161))

    def test_wake_phrase_and_command_in_same_utterance(self):
        dialogue = voice.Dialogue()
        self.assertEqual(
            dialogue.accept("Hello Jarvis, open YouTube.", 100, woke=True),
            "open YouTube.",
        )
        self.assertEqual(
            dialogue.accept("Hello Jarvis open Gmail", 200, woke=True), "open Gmail"
        )
        self.assertIsNone(dialogue.accept("open WhatsApp", 200.1))

    def test_substrings_and_unrelated_names_do_not_wake(self):
        dialogue = voice.Dialogue()
        for text in [
            "service open gmail",
            "Jarvison open gmail",
            "tell me about Jarvis",
            "Jarvis",
            "Hi Jarvis",
            "Hey Jarvis open WhatsApp",
            "Hello service",
            "Hello Jarvison",
            "HelloJarvis",
            "someone said hello jarvis",
        ]:
            self.assertIsNone(dialogue.accept(text, 100, woke=True))

    def test_sleep_commands_are_exact(self):
        self.assertIsNotNone(voice.SLEEP.fullmatch("stop listening"))
        self.assertIsNotNone(voice.SLEEP.fullmatch("Go to sleep."))
        self.assertIsNone(voice.SLEEP.fullmatch("explain how computers go to sleep"))

    def test_only_hello_jarvis_with_case_or_punctuation_changes(self):
        for phrase in ["Hello Jarvis!", "Hello, Jarvis.", "HELLO JARVIS"]:
            with self.subTest(phrase=phrase):
                self.assertEqual(voice.Dialogue().accept(phrase, 100, woke=True), "")
        self.assertEqual(
            voice.Dialogue().accept("Hello Jarvis, open ChatGPT", 100, woke=True),
            "open ChatGPT",
        )

    def test_fast_greeting_never_discards_a_command_or_uncertain_word(self):
        def part(text, confidence=1):
            return {
                "text": text,
                "result": [{"word": w, "conf": confidence} for w in text.split()],
            }

        self.assertEqual(voice.fast_greeting([part("hello jarvis")]), "hello jarvis")
        self.assertEqual(
            voice.fast_greeting([part("hello"), part("jarvis")]), "hello jarvis"
        )
        for item in [
            part("hello jarvis", 0.5),
            part("jarvis open chat gpt"),
            part("hello service"),
            {"text": "hello jarvis"},
        ]:
            self.assertIsNone(voice.fast_greeting([item]))

    def test_independent_recognition_requires_both_confident_wake_words(self):
        def part(text, confidence=1):
            return {
                "text": text,
                "result": [{"word": w, "conf": confidence} for w in text.split()],
            }

        self.assertTrue(voice.verified_wake([part("hello jarvis open whatsapp")]))
        self.assertTrue(voice.verified_wake([part("hello"), part("jarvis")]))
        for item in [
            part("hello jarvis", 0.84),
            part("jarvis open whatsapp"),
            part("hello service"),
            part("someone said hello jarvis"),
            {"text": "hello jarvis"},
            {"text": "hello jarvis", "result": [{"word": "hello", "conf": 1}]},
        ]:
            self.assertFalse(voice.verified_wake([item]))


class AudioTests(unittest.TestCase):
    def test_pre_wake_background_speech_is_trimmed_by_word_timestamp(self):
        frames = [(i.to_bytes(2, "little") * voice.BLOCK) for i in range(50)]
        seed, noise = voice.wake_seed(
            frames,
            4,
            {
                "partial_result": [
                    {"word": "hello", "start": 2.8},
                    {"word": "jarvis", "start": 3.2},
                ]
            },
            final=False,
        )
        self.assertEqual(len(seed), 17)
        self.assertIn(frames[35], seed)  # Keep "hello", not only "jarvis".
        self.assertEqual(seed[-1], frames[-1])
        self.assertNotIn(frames[0], seed)
        self.assertGreaterEqual(noise, 0.001)

    def test_soft_microphone_speech_still_ends_after_a_pause(self):
        detector = voice.TurnBoundary()
        for _ in range(8):
            detector.update(0.008)
        for _ in range(16):
            ended = detector.update(0.001)
        self.assertTrue(detector.started)
        self.assertTrue(ended)

    def test_keyboard_tap_does_not_create_a_command(self):
        detector = voice.TurnBoundary()
        detector.update(0.2)
        for _ in range(80):
            ended = detector.update(0.001)
        self.assertTrue(ended)
        self.assertFalse(detector.started)

    def test_short_pause_keeps_turn_and_long_pause_ends_it(self):
        detector = voice.TurnBoundary()
        for _ in range(7):
            detector.update(0.1)
        for _ in range(6):
            self.assertFalse(detector.update(0.001))
        detector.update(0.1)
        ended = False
        for _ in range(16):
            ended = detector.update(0.001)
        self.assertTrue(ended)
        self.assertTrue(detector.started)

    def test_continuous_sound_is_bounded(self):
        detector = voice.TurnBoundary()
        for _ in range(376):
            ended = detector.update(0.1)
        self.assertTrue(ended)

    def test_wav_contains_the_actual_recording_format(self):
        raw = b"\x01\x00" * voice.BLOCK
        with wave.open(io.BytesIO(voice.wav_bytes([raw])), "rb") as audio:
            self.assertEqual(
                (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()),
                (16000, 1, 2),
            )
            self.assertEqual(audio.readframes(voice.BLOCK), raw)

    def test_browser_lease_expires_after_crash_or_closed_tab(self):
        with tempfile.TemporaryDirectory() as folder:
            lease = Path(folder) / "lease.json"
            with patch.object(voice, "LEASE", lease):
                self.assertFalse(voice.browser_active(100))
                lease.write_text(json.dumps({"expires_at": 115}), "utf-8")
                self.assertTrue(voice.browser_active(100))
                self.assertFalse(voice.browser_active(116))
                lease.write_text("broken json", "utf-8")
                self.assertFalse(voice.browser_active(100))


class AgentRoutingTests(unittest.TestCase):
    def test_long_conversations_keep_recent_complete_turns(self):
        history = [
            {"role": role, "content": f"{i}: " + "x" * 300}
            for i in range(16)
            for role in ("user", "assistant")
        ]
        recent = voice.trim_history(history)
        self.assertLessEqual(len(recent), 20)
        self.assertLessEqual(sum(len(turn["content"]) for turn in recent), 6000)
        self.assertEqual(recent[0]["role"], "user")
        self.assertEqual(recent[-1], history[-1])

    def test_speech_does_not_read_reasoning_or_markdown(self):
        text = "<think>private reasoning</think>## Hey\n- I\x27m here.\n[Read this](https://example.com)"
        self.assertEqual(voice.spoken_text(text), "Hey I'm here. Read this")

    def agent(self):
        agent = voice.LocalAgent.__new__(voice.LocalAgent)
        agent.http = Mock()
        agent.history = []
        agent.job = None
        agent._speech_cache = {}
        return agent

    def test_wake_reply_reuses_audio_without_another_tts_request(self):
        agent = self.agent()
        agent.http.post.return_value.content = b"RIFFaudio"
        self.assertEqual(agent.speech(voice.WAKE_REPLY), b"RIFFaudio")
        self.assertEqual(agent.speech(voice.WAKE_REPLY), b"RIFFaudio")
        self.assertEqual(agent.http.post.call_count, 1)

    def test_desktop_command_uses_existing_executor_without_extra_model_call(self):
        agent = self.agent()
        agent.http.post.return_value.json.return_value = {
            "handled": True,
            "response": "I opened YouTube.",
        }
        self.assertEqual(agent.answer("open youtube"), "I opened YouTube.")
        self.assertEqual(agent.http.post.call_args.args[0], "/v1/desktop/command")
        self.assertTrue(
            agent.http.post.call_args.kwargs["json"]["id"].startswith("background-")
        )
        agent.http.get.assert_not_called()
        self.assertIsNone(agent.job)

    def test_questions_use_local_chat_and_preserve_followup_context(self):
        agent = self.agent()
        desktop = Mock()
        desktop.json.return_value = {"handled": False}
        chat = Mock()
        chat.json.return_value = {"choices": [{"message": {"content": "Hello there."}}]}
        agent.http.post.side_effect = [desktop, chat]
        agent.http.get.return_value.json.return_value = {
            "data": [{"id": "llama3.2:latest"}]
        }
        self.assertEqual(agent.answer("Hello"), "Hello there.")
        args = agent.http.post.call_args.kwargs["json"]
        self.assertEqual(args["model"], "llama3.2:latest")
        self.assertEqual(args["messages"], [{"role": "user", "content": "Hello"}])
        self.assertEqual(len(agent.history), 2)

    def test_failed_action_does_not_leak_running_job_or_claim_success(self):
        agent = self.agent()
        agent.http.post.side_effect = RuntimeError("backend unavailable")
        with self.assertRaises(RuntimeError):
            agent.answer("open gmail")
        self.assertIsNone(agent.job)
        self.assertEqual(agent.history, [])


class MicrophoneControlTests(unittest.TestCase):
    def test_fast_wake_response_needs_neither_whisper_nor_chat_model(self):
        import types

        listener = voice.BackgroundVoice()
        listener.agent = Mock()
        listener.ready.set()
        listener.allowed = Mock(return_value=True)

        def capture(*args, **kwargs):
            self.assertTrue(kwargs["wake"])
            listener.fast_text = "hello jarvis"
            listener.wake_verified = True
            return b"recorded microphone audio"

        listener.capture = capture
        listener.speak = Mock(
            side_effect=lambda text: (
                listener.stop.set() if text == voice.WAKE_REPLY else None
            )
        )
        model = Mock()
        model.vosk_model_find_word.return_value = 1
        vosk = types.SimpleNamespace(
            Model=Mock(return_value=model), KaldiRecognizer=Mock(), SetLogLevel=Mock()
        )
        with patch.dict("sys.modules", {"vosk": vosk}):
            listener.listen()
        listener.agent.transcribe.assert_not_called()
        listener.agent.answer.assert_not_called()
        listener.speak.assert_called_once_with(voice.WAKE_REPLY)

    def test_false_wake_does_not_transcribe_answer_or_speak_on_startup(self):
        import types

        listener = voice.BackgroundVoice()
        listener.agent = Mock()
        listener.ready.set()
        listener.allowed = Mock(return_value=True)
        listener.speak = Mock()

        def capture(*args, **kwargs):
            listener.fast_text = "hello jarvis"
            listener.wake_verified = False
            listener.stop.set()
            return b"ambient noise"

        listener.capture = capture
        model = Mock()
        model.vosk_model_find_word.return_value = 1
        vosk = types.SimpleNamespace(
            Model=Mock(return_value=model), KaldiRecognizer=Mock(), SetLogLevel=Mock()
        )
        with patch.dict("sys.modules", {"vosk": vosk}):
            listener.listen()
        listener.agent.transcribe.assert_not_called()
        listener.agent.answer.assert_not_called()
        listener.speak.assert_not_called()

    def test_chat_warmup_does_not_delay_microphone_readiness(self):
        listener = voice.BackgroundVoice()
        listener.agent = Mock()

        def warm():
            self.assertTrue(listener.ready.is_set())
            listener.stop.set()

        listener.agent.warm.side_effect = warm
        listener.supervise_backend()

    def test_listener_returns_to_wake_mode_after_every_answer(self):
        import types

        listener = voice.BackgroundVoice()
        listener.agent = Mock()
        listener.agent.transcribe.side_effect = [
            "Hello Jarvis, open WhatsApp",
            "tell me about the weather",
            "Hello Jarvis, open YouTube",
        ]
        listener.agent.answer.return_value = "Done."
        listener.ready.set()
        listener.allowed = Mock(return_value=True)
        listener.speak = Mock()
        count = 0

        def capture(*args, **kwargs):
            nonlocal count
            self.assertTrue(kwargs["wake"])
            count += 1
            listener.wake_verified = True
            if count == 3:
                listener.stop.set()
            return b"synthetic audio"

        listener.capture = capture
        model = Mock()
        model.vosk_model_find_word.return_value = 1
        vosk = types.SimpleNamespace(
            Model=Mock(return_value=model), KaldiRecognizer=Mock(), SetLogLevel=Mock()
        )
        with patch.dict("sys.modules", {"vosk": vosk}):
            listener.listen()
        self.assertEqual(
            [call.args[0] for call in listener.agent.answer.call_args_list],
            ["open WhatsApp", "open YouTube"],
        )
        self.assertEqual(listener.speak.call_count, 2)

    def test_lock_pause_and_browser_voice_all_release_background_capture(self):
        listener = voice.BackgroundVoice.__new__(voice.BackgroundVoice)
        listener.stop = threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            paused, stop = Path(folder) / "paused", Path(folder) / "stop"
            with (
                patch.object(voice, "PAUSED", paused),
                patch.object(voice, "STOP", stop),
                patch.object(voice, "browser_active", return_value=False) as browser,
                patch.object(voice, "unlocked", return_value=True) as unlocked,
            ):
                self.assertTrue(listener.allowed())
                unlocked.return_value = False
                self.assertFalse(listener.allowed())
                unlocked.return_value = True
                browser.return_value = True
                self.assertFalse(listener.allowed())
                browser.return_value = False
                paused.touch()
                self.assertFalse(listener.allowed())
                paused.unlink()
                stop.touch()
                self.assertFalse(listener.allowed())


if __name__ == "__main__":
    unittest.main()
