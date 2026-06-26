from __future__ import annotations

import json
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

CFT_LAST_KNOWN_GOOD_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"


@dataclass(slots=True)
class BrowserBundlePaths:
    chrome_binary: Path | None = None
    chromedriver: Path | None = None

    @property
    def is_complete(self) -> bool:
        return bool(
            self.chrome_binary
            and self.chromedriver
            and self.chrome_binary.exists()
            and self.chromedriver.exists()
        )


def app_base_dir() -> Path:
    """Return the directory where portable runtime assets should live."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path.cwd()


def candidate_bundle_roots(base_dir: str | os.PathLike[str] | None = None) -> list[Path]:
    base = Path(base_dir) if base_dir else app_base_dir()
    roots = [base]
    # In development, also search the repository root even when cwd is a subdirectory.
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            roots.append(parent)
            break
    unique: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique


def find_bundled_browser(base_dir: str | os.PathLike[str] | None = None) -> BrowserBundlePaths:
    env_chrome = os.environ.get("NAVER_CHROME_BINARY") or os.environ.get("CHROME_BINARY")
    env_driver = os.environ.get("NAVER_CHROMEDRIVER") or os.environ.get("CHROMEDRIVER")
    if env_chrome or env_driver:
        return BrowserBundlePaths(
            chrome_binary=Path(env_chrome) if env_chrome else None,
            chromedriver=Path(env_driver) if env_driver else None,
        )

    for root in candidate_bundle_roots(base_dir):
        chrome = root / "browsers" / "chrome-win64" / "chrome.exe"
        driver = root / "drivers" / "chromedriver-win64" / "chromedriver.exe"
        if chrome.exists() and driver.exists():
            return BrowserBundlePaths(chrome, driver)
    return BrowserBundlePaths()


def _pick_download(downloads: dict, product: str, platform: str = "win64") -> str:
    for item in downloads.get(product, []):
        if item.get("platform") == platform and item.get("url"):
            return str(item["url"])
    raise RuntimeError(f"Chrome for Testing download not found: {product}/{platform}")


def chrome_for_testing_urls(channel: str = "Stable") -> tuple[str, str, str]:
    with urlopen(CFT_LAST_KNOWN_GOOD_URL, timeout=30) as response:  # noqa: S310 - trusted public metadata URL
        payload = json.loads(response.read().decode("utf-8"))
    channel_data = payload.get("channels", {}).get(channel)
    if not isinstance(channel_data, dict):
        raise RuntimeError(f"Chrome for Testing channel not found: {channel}")
    downloads = channel_data.get("downloads", {})
    return (
        str(channel_data.get("version", "")),
        _pick_download(downloads, "chrome"),
        _pick_download(downloads, "chromedriver"),
    )


def _download_zip(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url, timeout=120) as response, dest.open("wb") as fp:  # noqa: S310 - trusted URL from CfT metadata
        shutil.copyfileobj(response, fp)


def _extract_zip(zip_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)


def ensure_chrome_for_testing_bundle(
    target_dir: str | os.PathLike[str],
    *,
    channel: str = "Stable",
    force: bool = False,
) -> BrowserBundlePaths:
    """Download Chrome for Testing + matching ChromeDriver into a portable app folder.

    The resulting layout is:
    - browsers/chrome-win64/chrome.exe
    - drivers/chromedriver-win64/chromedriver.exe
    """
    target = Path(target_dir)
    paths = find_bundled_browser(target)
    if paths.is_complete and not force:
        return paths

    version, chrome_url, driver_url = chrome_for_testing_urls(channel)
    download_dir = target / "_browser_downloads"
    chrome_zip = download_dir / f"chrome-{version}-win64.zip"
    driver_zip = download_dir / f"chromedriver-{version}-win64.zip"
    extract_tmp = target / "_browser_extract"

    if force:
        shutil.rmtree(target / "browsers", ignore_errors=True)
        shutil.rmtree(target / "drivers", ignore_errors=True)
        shutil.rmtree(extract_tmp, ignore_errors=True)

    _download_zip(chrome_url, chrome_zip)
    _download_zip(driver_url, driver_zip)
    shutil.rmtree(extract_tmp, ignore_errors=True)
    _extract_zip(chrome_zip, extract_tmp / "chrome")
    _extract_zip(driver_zip, extract_tmp / "chromedriver")

    chrome_src = extract_tmp / "chrome" / "chrome-win64"
    driver_src = extract_tmp / "chromedriver" / "chromedriver-win64"
    if not (chrome_src / "chrome.exe").exists():
        raise RuntimeError(f"Downloaded Chrome archive did not contain chrome.exe: {chrome_src}")
    if not (driver_src / "chromedriver.exe").exists():
        raise RuntimeError(f"Downloaded ChromeDriver archive did not contain chromedriver.exe: {driver_src}")

    target_browsers = target / "browsers"
    target_drivers = target / "drivers"
    target_browsers.mkdir(parents=True, exist_ok=True)
    target_drivers.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(target_browsers / "chrome-win64", ignore_errors=True)
    shutil.rmtree(target_drivers / "chromedriver-win64", ignore_errors=True)
    shutil.move(str(chrome_src), str(target_browsers / "chrome-win64"))
    shutil.move(str(driver_src), str(target_drivers / "chromedriver-win64"))
    shutil.rmtree(extract_tmp, ignore_errors=True)

    return find_bundled_browser(target)
