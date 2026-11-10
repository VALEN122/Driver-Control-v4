import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_alignment_module():
    path = ROOT / "scripts/android/check_elf_alignment.py"
    spec = importlib.util.spec_from_file_location("check_elf_alignment", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseToolchainTest(unittest.TestCase):
    def test_api36_keeps_p4a_and_ndk_pinned(self):
        spec = (ROOT / "buildozer.spec").read_text(encoding="utf-8")
        self.assertIn("android.api = 36", spec)
        self.assertIn("android.ndk = 25b", spec)
        self.assertIn("p4a.branch = v2024.01.21", spec)

    def test_p4a_patch_updates_only_packaging_and_alignment_layers(self):
        patch = (ROOT / "patches/p4a-v2024.01.21-api36.patch").read_text(
            encoding="utf-8"
        )
        self.assertIn("com.android.tools.build:gradle:8.9.1", patch)
        self.assertIn("gradle-8.11.1-all.zip", patch)
        self.assertIn("max-page-size=16384", patch)
        self.assertNotIn("recipes/python3/__init__.py", patch)
        self.assertNotIn("recipes/openssl/__init__.py", patch)

    def test_alignment_parser_reads_load_segments(self):
        module = _load_alignment_module()
        output = """
  LOAD 0x000000 0x0 0x0 0x100 0x100 R E 0x4000
  LOAD 0x004000 0x4000 0x4000 0x80 0x80 RW 0x10000
"""
        self.assertEqual([0x4000, 0x10000], module.load_alignments(output))

    def test_alignment_parser_detects_old_4k_binary(self):
        module = _load_alignment_module()
        output = "  LOAD 0x0 0x0 0x0 0x10 0x10 R E 0x1000\n"
        self.assertLess(min(module.load_alignments(output)), module.MIN_ALIGNMENT)


if __name__ == "__main__":
    unittest.main()
