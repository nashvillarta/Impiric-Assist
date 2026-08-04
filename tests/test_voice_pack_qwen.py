"""Guards the --engine qwen path against the real qwen-tts API.

The generator's qwen branch cannot be exercised end-to-end in a test (it needs
a multi-gigabyte checkpoint), so these tests stand in a fake qwen_tts module
that mirrors the shape of the real one: Qwen3TTSModel.from_pretrained(...) and
.generate_custom_voice(...) -> (list[np.ndarray], sample_rate). That is enough
to catch the failure this file was written for -- calling an API that does not
exist -- which no amount of --engine native testing would have surfaced.
"""

import os
import sys
import types
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from tools import generate_voice_pack


FAKE_RATE = 24000


class FakeTTS:
    """Mirrors the parts of qwen_tts.Qwen3TTSModel the generator relies on."""

    instances = []

    def __init__(self, model):
        self.model = model
        self.calls = []
        self.instructs = []
        FakeTTS.instances.append(self)

    load_kwargs = []

    @classmethod
    def from_pretrained(cls, model, **kwargs):
        cls.load_kwargs.append(kwargs)
        return cls(model)

    def generate_custom_voice(self, text, speaker, **kwargs):
        self.calls.append((text, speaker))
        self.instructs.append(kwargs.get("instruct"))
        # A quarter second of quiet tone, as float32 in [-1, 1] like the real one.
        t = np.linspace(0, 0.25, FAKE_RATE // 4, endpoint=False, dtype=np.float32)
        return [np.sin(2 * np.pi * 220 * t, dtype=np.float32) * 0.5], FAKE_RATE


class TestQwenEngine(unittest.TestCase):
    def setUp(self):
        FakeTTS.instances = []
        FakeTTS.load_kwargs = []
        fake_module = types.ModuleType("qwen_tts")
        fake_module.Qwen3TTSModel = FakeTTS
        self.addCleanup(sys.modules.pop, "qwen_tts", None)
        sys.modules["qwen_tts"] = fake_module
        self.out_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "_qwen_tmp"
        )
        os.makedirs(self.out_dir, exist_ok=True)
        self.addCleanup(self._clean_out_dir)

    def _clean_out_dir(self):
        for name in os.listdir(self.out_dir):
            os.remove(os.path.join(self.out_dir, name))
        os.rmdir(self.out_dir)

    def _out(self, name):
        return os.path.join(self.out_dir, name)

    def test_speak_qwen_writes_a_playable_pcm_wav(self):
        """winsound.PlaySound only handles PCM, so float32 samples must be
        converted rather than written through."""
        path = self._out("line.wav")
        generate_voice_pack.speak_qwen("Okay.", path, "some/model", "Serena", engine_state={})

        self.assertTrue(os.path.exists(path))
        with wave.open(path, "rb") as w:
            self.assertEqual(w.getsampwidth(), 2, "must be 16-bit PCM")
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getframerate(), FAKE_RATE)
            self.assertGreater(w.getnframes(), 0)

    def test_speak_qwen_passes_the_voice_through_as_speaker(self):
        generate_voice_pack.speak_qwen(
            "Okay.", self._out("line.wav"), "some/model", "Serena", engine_state={}
        )
        self.assertEqual(FakeTTS.instances[0].calls, [("Okay.", "Serena")])

    def test_speak_qwen_reports_the_models_real_sample_rate(self):
        rate = generate_voice_pack.speak_qwen(
            "Okay.", self._out("line.wav"), "some/model", "Serena", engine_state={}
        )
        self.assertEqual(rate, FAKE_RATE)

    def test_model_is_loaded_once_and_reused(self):
        state = {}
        generate_voice_pack.speak_qwen("One.", self._out("a.wav"), "m", "Serena", engine_state=state)
        generate_voice_pack.speak_qwen("Two.", self._out("b.wav"), "m", "Serena", engine_state=state)
        self.assertEqual(len(FakeTTS.instances), 1, "checkpoint must not reload per line")

    def test_default_model_is_the_preset_speaker_checkpoint(self):
        """--voice Serena names a preset speaker, which only the CustomVoice
        checkpoint supports; the Base checkpoint rejects generate_custom_voice."""
        parser_default = generate_voice_pack.DEFAULT_MODEL
        self.assertIn("CustomVoice", parser_default)

    def _fake_torch(self, cuda_available):
        fake = types.ModuleType("torch")
        fake.cuda = types.SimpleNamespace(is_available=lambda: cuda_available)
        real = sys.modules.get("torch")
        self.addCleanup(
            lambda: sys.modules.__setitem__("torch", real)
            if real is not None
            else sys.modules.pop("torch", None)
        )
        sys.modules["torch"] = fake

    def test_model_goes_to_the_gpu_when_one_is_available(self):
        """The pack is meant to be generated on a CUDA box (see README); loading
        a 1.7B model on the CPU by default makes a 36-line run take hours."""
        self._fake_torch(True)
        generate_voice_pack.speak_qwen(
            "Okay.", self._out("a.wav"), "m", "Serena", engine_state={}
        )
        self.assertEqual(FakeTTS.load_kwargs[0].get("device_map"), "cuda")

    def test_cpu_only_torch_still_loads(self):
        """A CPU-only torch build must not be asked for cuda -- that raises."""
        self._fake_torch(False)
        generate_voice_pack.speak_qwen(
            "Okay.", self._out("a.wav"), "m", "Serena", engine_state={}
        )
        self.assertNotIn("device_map", FakeTTS.load_kwargs[0])

    def test_instruct_is_passed_to_the_model(self):
        """--instruct is how a preset speaker gets steered toward a character
        voice; if it silently never reaches the model the run still 'works' and
        produces the wrong voice, which is the failure worth guarding."""
        generate_voice_pack.speak_qwen(
            "Okay.",
            self._out("a.wav"),
            "m",
            "Aiden",
            instruct="A calm British AI assistant.",
            engine_state={},
        )
        self.assertEqual(
            FakeTTS.instances[0].instructs, ["A calm British AI assistant."]
        )

    def test_no_instruct_sends_none(self):
        generate_voice_pack.speak_qwen(
            "Okay.", self._out("a.wav"), "m", "Aiden", engine_state={}
        )
        self.assertEqual(FakeTTS.instances[0].instructs, [None])

    def test_instruct_reaches_the_model_through_main(self):
        generate_voice_pack.main_with_args(
            [
                "--engine", "qwen",
                "--voice", "Aiden",
                "--instruct", "Crisp British RP.",
                "--out", self.out_dir,
            ]
        )
        import voice_lines

        instructs = FakeTTS.instances[0].instructs
        # Derived, not hardcoded: the line count changes whenever a new action
        # is added, and this test is not about how many lines there are.
        self.assertEqual(len(instructs), len(voice_lines.all_speech_lines()))
        self.assertEqual(set(instructs), {"Crisp British RP."})

    def test_manifest_records_the_instruct(self):
        """The instruct is the only record of why the pack sounds the way it
        does -- without it a rerun cannot reproduce the voice."""
        import json

        generate_voice_pack.main_with_args(
            [
                "--engine", "qwen",
                "--voice", "Aiden",
                "--instruct", "Crisp British RP.",
                "--out", self.out_dir,
            ]
        )
        with open(os.path.join(self.out_dir, "manifest.json")) as f:
            manifest = json.load(f)
        self.assertEqual(manifest["instruct"], "Crisp British RP.")

    def test_native_engine_rejects_instruct(self):
        """Windows SAPI has no notion of a style instruction; accepting one
        silently would imply it did something."""
        with self.assertRaises(SystemExit):
            generate_voice_pack.main_with_args(
                ["--engine", "native", "--instruct", "Crisp British RP.",
                 "--out", self.out_dir]
            )

    def test_manifest_records_the_generated_sample_rate(self):
        import json

        generate_voice_pack.main_with_args(
            ["--engine", "qwen", "--voice", "Serena", "--out", self.out_dir]
        )
        with open(os.path.join(self.out_dir, "manifest.json")) as f:
            manifest = json.load(f)
        self.assertEqual(manifest["sample_rate"], FAKE_RATE)
        self.assertEqual(manifest["voice"], "Serena")


if __name__ == "__main__":
    unittest.main()
