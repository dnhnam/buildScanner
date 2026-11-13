import subprocess
import sys
from pathlib import Path

from scanner import core
from synth import make_photo

ROOT = Path(__file__).resolve().parent.parent


def test_cli_folder_to_pdf(tmp_path):
    src = tmp_path / "ảnh"
    src.mkdir()
    for i in (1, 2, 10):
        photo, _ = make_photo(seed=i)
        core.save_image(photo, src / f"trang{i}.jpg")
    out = tmp_path / "kết quả.pdf"
    r = subprocess.run([sys.executable, str(ROOT / "scan_cli.py"), str(src), "-o", str(out), "--mode", "bw"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert out.read_bytes().startswith(b"%PDF")
    lines = [l for l in r.stdout.splitlines() if l.strip().startswith("[")]
    assert [l.split()[1] for l in lines] == ["trang1.jpg", "trang2.jpg", "trang10.jpg"]  # sắp theo số tự nhiên
