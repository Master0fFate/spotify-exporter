# The exporter never plays media or renders PDFs. Keep those optional stacks out.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

root = Path(SPECPATH).parent
hidden = collect_submodules(
    'qfluentwidgets', filter=lambda name: not name.startswith('qfluentwidgets.multimedia')
) + collect_submodules('qframelesswindow')

a = Analysis(
    [str(root / 'spotify_exporter.py')],
    pathex=[str(root)],
    datas=collect_data_files('qfluentwidgets') + collect_data_files('qframelesswindow')
    + copy_metadata('PyQt6-Fluent-Widgets'),
    hiddenimports=hidden,
    excludes=['qfluentwidgets.multimedia', 'PyQt6.QtMultimedia',
              'PyQt6.QtMultimediaWidgets', 'PyQt6.QtPdf', 'PyQt6.QtPdfWidgets',
              'win32ui', 'pywin', 'pythonwin', 'PyQt6.QtOpenGL', 'PyQt6.QtOpenGLWidgets'],
)
# Pythonwin's optional COM browser pulls in MFC, but none of our window paths use it.
# QtGui's general image-format hook otherwise adds qpdf.dll and Qt6Pdf.dll,
# even though no application feature consumes PDFs. PNG/JPEG/SVG/ICO remain.
# All screens use raster QWidget/QPainter rendering, never QOpenGLWidget.
excluded_binaries = {'qpdf.dll', 'qt6pdf.dll', 'qt6pdfwidgets.dll', 'opengl32sw.dll'}
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() not in excluded_binaries]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name='SpotifyExporter',
          console=False, debug=False, strip=False, upx=False,
          icon=str(root / 'icon.ico'))
