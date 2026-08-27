import json
import os
import subprocess
import urllib.request
from pathlib import Path

from qgis.PyQt.QtCore import QObject, pyqtSignal, pyqtSlot


class CatalogWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, url):
        super().__init__()
        self.url = url

    @pyqtSlot()
    def run(self):
        try:
            self.status.emit("Geofabrik-Katalog wird geladen …")
            req = urllib.request.Request(self.url, headers={"User-Agent": "OfflineMapGenerator-QGIS/0.2"})
            with urllib.request.urlopen(req, timeout=60) as response:
                data = json.load(response)
            self.finished.emit(data)
        except Exception as exc:
            self.failed.emit(str(exc))


class BuildWorker(QObject):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    def _check_cancel(self):
        if self.cancelled:
            raise RuntimeError("Vorgang wurde abgebrochen.")

    def _download(self, url, target):
        target = Path(target)
        temp = target.with_suffix(target.suffix + ".part")
        if temp.exists():
            temp.unlink()
        req = urllib.request.Request(url, headers={"User-Agent": "OfflineMapGenerator-QGIS/0.2"})
        with urllib.request.urlopen(req, timeout=120) as response, temp.open("wb") as out:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while True:
                self._check_cancel()
                block = response.read(1024 * 1024)
                if not block:
                    break
                out.write(block)
                done += len(block)
                if total:
                    pct = 5 + int(35 * done / total)
                    self.progress.emit(min(pct, 40))
                    self.log.emit(f"Download: {done / 1048576:.1f} / {total / 1048576:.1f} MiB")
        temp.replace(target)

    def _run_command(self, command, label):
        self._check_cancel()
        self.log.emit("\n" + label)
        self.log.emit(" ".join(f'"{str(x)}"' if " " in str(x) else str(x) for x in command))
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", creationflags=flags)
        assert proc.stdout is not None
        for line in proc.stdout:
            self.log.emit(line.rstrip())
            if self.cancelled:
                proc.terminate()
                raise RuntimeError("Vorgang wurde abgebrochen.")
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"{label} fehlgeschlagen (Exit-Code {code}).")

    @pyqtSlot()
    def run(self):
        try:
            c = self.config
            out = Path(c["output"])
            out.mkdir(parents=True, exist_ok=True)
            source = Path(c["source_pbf"])
            if c.get("download_url"):
                source = out / c["download_filename"]
                if source.exists() and c.get("reuse_download", True):
                    self.log.emit(f"Vorhandener Download wird verwendet: {source}")
                    self.progress.emit(40)
                else:
                    self.log.emit(f"Download: {c['download_url']}")
                    self._download(c["download_url"], source)
            self._check_cancel()

            clipped = out / f"{c['name']}.osm.pbf"
            gpkg = out / f"{c['name']}.gpkg"
            bbox = ",".join(f"{v:.8f}" for v in c["bbox"])
            self.progress.emit(43)
            self._run_command([
                c["osmium"], "extract", "--bbox", bbox,
                "--strategy", "complete_ways", "--set-bounds", "--overwrite",
                "--output", str(clipped), str(source)
            ], "PBF auf Kartenausschnitt zuschneiden")
            self.progress.emit(65)

            if c["create_gpkg"]:
                if gpkg.exists():
                    gpkg.unlink()
                self._run_command([
                    c["ogr2ogr"], "-f", "GPKG", str(gpkg), str(clipped),
                    "-lco", "SPATIAL_INDEX=YES", "-oo", "INTERLEAVED_READING=YES"
                ], "GeoPackage erzeugen")
            self.progress.emit(92)

            if not c["keep_clipped"] and clipped.exists():
                clipped.unlink()
            if c.get("delete_download") and c.get("download_url") and source.exists():
                source.unlink()
            self.progress.emit(100)
            self.finished.emit(str(gpkg if c["create_gpkg"] else clipped))
        except Exception as exc:
            self.failed.emit(str(exc))
