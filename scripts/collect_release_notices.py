"""Copy installed license texts verbatim; inventory is not a compliance guarantee."""

import importlib.metadata
import json
import os
import platform
import shutil
import sys
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

root = Path("dist/third-party-notices")
root.mkdir(parents=True, exist_ok=True)
records = []
for distribution in sorted(
    importlib.metadata.distributions(), key=lambda d: d.metadata["Name"].lower()
):
    name, version = distribution.metadata["Name"], distribution.version
    record = {
        "name": name,
        "version": version,
        "license_expression": distribution.metadata.get("License-Expression"),
        "license_metadata": distribution.metadata.get("License"),
        "project_urls": distribution.metadata.get_all("Project-URL", []),
        "pypi_version_page": f"https://pypi.org/project/{name}/{version}/",
        "license_files": [],
    }
    for entry in distribution.files or []:
        filename = Path(str(entry)).name.lower()
        if not filename.startswith(("license", "copying", "notice", "copyright")):
            continue
        source = Path(distribution.locate_file(entry))
        if source.is_file():
            target = (
                root
                / "installed-distributions"
                / f"{name}-{version}"
                / str(entry).replace("..", "_parent_")
            )
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            record["license_files"].append(str(target.relative_to(root)))
    records.append(record)
for source in (Path(sys.base_prefix) / "LICENSE.txt", Path(sys.base_prefix) / "LICENSE"):
    if source.is_file():
        shutil.copyfile(source, root / f"Python-{platform.python_version()}-{source.name}")
        break
else:
    raise RuntimeError("Installed Python license text not found")
shutil.copyfile("LICENSE", root / "Spotify-Exporter-MIT-LICENSE")
archive = CArchiveReader("dist/SpotifyExporter.exe")
names = sorted(archive.toc)
for name in names:
    if any(
        token in name.lower()
        for token in (
            "qt6multimedia",
            "qt6pdf",
            "ffmpeg",
            "avcodec-",
            "avformat-",
            "avutil-",
            "swresample-",
            "swscale-",
            "win32ui",
            "pythonwin",
            "mfc140",
        )
    ):
        raise RuntimeError(f"Unused native dependency still bundled: {name}")
(root / "bundled-file-inventory.txt").write_text("\n".join(names), encoding="utf-8")
(root / "installed-distribution-inventory.json").write_text(
    json.dumps(records, indent=2), encoding="utf-8"
)
(root / "build-provenance.json").write_text(
    json.dumps(
        {
            "source_sha": os.environ.get("GITHUB_SHA"),
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
        indent=2,
    ),
    encoding="utf-8",
)
(root / "README.txt").write_text(
    """THIRD-PARTY LICENSE INVENTORY — REVIEW REQUIRED

The application's existing MIT source license is preserved verbatim.
This companion copies license/notice texts from the actual Windows build environment,
including Python. Installed-distribution inventory includes build tools and packages
that may not be present in the executable; bundled-file-inventory lists its native/data
archive. Python modules inside PYZ require the corresponding source/build inventory too.

PyQt6, QFluentWidgets and FramelessWindow have GPL terms; bundled Qt has LGPL terms.
The executable is NOT represented as MIT-only. These notices do not by themselves
satisfy all corresponding-source, Qt third-party-code or relinking obligations.
No new license grant, source-availability promise or commercial license is asserted.
The GPL binary release must also include its corresponding-source and full native-notice
companion assets. This automated inventory is only one input to that release package.

Build/reproduction: repository commit in build-provenance.json, packaging/SpotifyExporter.spec,
scripts/build_windows.ps1 and .github/workflows/windows-package.yml.
Exact dependency versions and upstream project links are in the inventory.
Qt 6.11.2 source: https://download.qt.io/archive/qt/6.11/6.11.2/single/
Qt third-party code: https://doc.qt.io/qt-6.11/licenses-used-in-qt.html
Python source: https://www.python.org/downloads/
PyQt licensing: https://www.riverbankcomputing.com/commercial/license-faq

Publication remains separate from this build workflow.
""",
    encoding="utf-8",
)
shutil.make_archive("dist/SpotifyExporter-ThirdPartyNotices", "zip", root)
print(f"Collected installed license texts from {len(records)} distribution records")
