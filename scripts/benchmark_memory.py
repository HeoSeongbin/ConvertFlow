"""Linux container benchmark: fresh interpreter per sample, deterministic fixture.

python benchmark_memory.py /tmp/phase4_converter.py
Baseline must be an exported previous converter, never imported by product code.
"""

import hashlib
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from PIL import Image, ImageChops
from pypdf import PdfReader
from app.converters.image_pdf import ImagePDFConverter
from app.storage.checksums import checksum


def child(mode, source, output, baseline):
    if mode == "convert-baseline":
        spec = importlib.util.spec_from_file_location("phase4_converter", baseline)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        converter = module.ImagePDFConverter()
    else:
        converter = ImagePDFConverter()
    started = time.perf_counter()
    if mode.startswith("convert"):
        converter.convert(Path(source), Path(output))
        digest = None
    else:
        digest = (
            hashlib.sha256(Path(source).read_bytes()).hexdigest()
            if mode == "hash-baseline"
            else checksum(Path(source))
        )
    elapsed = time.perf_counter() - started
    # ru_maxrss can retain the parent's pre-exec peak after fork. VmHWM
    # measures this exec's address space and avoids contaminating comparisons.
    peak = (
        int(
            next(
                line.split()[1]
                for line in Path("/proc/self/status").read_text().splitlines()
                if line.startswith("VmHWM:")
            )
        )
        * 1024
    )
    evidence = {}
    if mode.startswith("convert"):
        reader = PdfReader(output, strict=True)
        evidence = {
            "pages": len(reader.pages),
            "imageHashes": [
                hashlib.sha256(page.images[0].data).hexdigest() for page in reader.pages
            ],
        }
    print(
        json.dumps(
            {
                "elapsedSeconds": elapsed,
                "peakProcessRssBytes": peak,
                "digest": digest,
                **evidence,
            }
        )
    )


def main(baseline):
    with tempfile.TemporaryDirectory(prefix="phase5-memory-") as directory:
        root = Path(directory)
        gradient = Image.linear_gradient("L").resize((2048, 2048))
        frames = [
            Image.merge(
                "RGB",
                (
                    ImageChops.offset(gradient, 0, i * 60),
                    gradient.transpose(Image.Transpose.ROTATE_90),
                    gradient,
                ),
            )
            for i in range(8)
        ]
        source = root / "fixture.tiff"
        frames[0].save(
            source, save_all=True, append_images=frames[1:], compression="tiff_deflate"
        )
        for frame in frames:
            frame.close()
        binary = root / "hash-fixture.bin"
        with binary.open("wb") as stream:
            for _ in range(64):
                stream.write(b"a" * 1024 * 1024)
        report = {
            "platform": "Linux Python fresh process",
            "fixture": {
                "format": "RGB TIFF",
                "pages": 8,
                "width": 2048,
                "height": 2048,
                "inputBytes": source.stat().st_size,
            },
            "hashFixtureBytes": binary.stat().st_size,
            "samples": {},
        }
        for mode in [
            "convert-baseline",
            "convert-current",
            "hash-baseline",
            "hash-current",
        ]:
            samples = []
            for _ in range(3):
                result = subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "--child",
                        mode,
                        str(source if mode.startswith("convert") else binary),
                        str(root / "output.pdf"),
                        baseline,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                samples.append(json.loads(result.stdout))
            report["samples"][mode] = {
                "medianSeconds": statistics.median(
                    item["elapsedSeconds"] for item in samples
                ),
                "medianPeakRssBytes": statistics.median(
                    item["peakProcessRssBytes"] for item in samples
                ),
                "runs": samples,
            }
        samples = report["samples"]
        assert (
            samples["convert-baseline"]["runs"][0]["imageHashes"]
            == samples["convert-current"]["runs"][0]["imageHashes"]
        )
        assert all(
            run["pages"] == 8
            for mode in ["convert-baseline", "convert-current"]
            for run in samples[mode]["runs"]
        )
        assert (
            samples["hash-baseline"]["runs"][0]["digest"]
            == samples["hash-current"]["runs"][0]["digest"]
        )
        report["equivalentPagesImagesAndHashes"] = True
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if sys.argv[1] == "--child":
        child(*sys.argv[2:])
    else:
        main(sys.argv[1])
