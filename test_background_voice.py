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

    def test_standalone_jarvis_opens_conversation(self):
        dialogue = voice.Dialogue()
        self.assertEqual(dialogue.accept("Jarvis.", 100, woke=True), "")
        self.assertEqual(dialogue.accept("what time is it?", 101), "what time is it?")
        self.assertEqual(dialogue.accept("tell me more", 159), "tell me more")
        self.assertIsNone(dialogue.accept("open gmail", 161))

    def test_wake_phrase_and_command_in_same_utterance(self):
        dialogue = voice.Dialogue()
        self.assertEqual(
            dialogue.accept("Hey Jarvis, open YouTube.", 100, woke=True),
            "open YouTube.",
        )
        self.assertEqual(
            dialogue.accept("Jarvis open Gmail", 200, woke=True), "open Gmail"
        )

    def test_substrings_and_unrelated_names_do_not_wake(self):
        dialogue = voice.Dialogue()
        for text in [
            "service open gmail",
            "Jarvison open gmail",
            "tell me about Jarvis",
        ]:
            self.assertIsNone(dialogue.accept(text, 100, woke=True))

    def test_sleep_commands_are_exact(self):
        self.assertIsNotNone(voice.SLEEP.fullmatch("stop listening"))
        self.assertIsNotNone(voice.SLEEP.fullmatch("Go to sleep."))
        self.assertIsNone(voice.SLEEP.fullmatch("explain how computers go to sleep"))


class AudioTests(unittest.TestCase):
    def test_pre_wake_background_speech_is_trimmed_by_word_timestamp(self):
        frames = [(i.to_bytes(2, "little") * voice.BLOCK) for i in range(50)]
        seed, noise = voice.wake_seed(
            frames,
            4,
            {"partial_result": [{"word": "jarvis", "start": 3.2}]},
            final=False,
        )
        self.assertLessEqual(len(seed), 12)
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
        return agent

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
