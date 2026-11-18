"""Check repository invariants and distinguish an offline candidate from a release."""

import argparse
import asyncio
import json
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from string import Formatter
from tempfile import TemporaryDirectory

from homeassistant import loader
from homeassistant.core import HomeAssistant
from homeassistant.helpers.translation import async_get_translations
from PIL import Image

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--candidate", action="store_true")
args = parser.parse_args()
errors = []
pending = []
component = root / "custom_components/viega_fonterra_modbus"
manifest = json.loads((component / "manifest.json").read_text(encoding="utf-8"))
hacs = json.loads((root / "hacs.json").read_text(encoding="utf-8"))
if [
    p.name
    for p in (root / "custom_components").iterdir()
    if p.is_dir() and not p.name.startswith("_")
] != ["viega_fonterra_modbus"]:
    errors.append("Repository must contain exactly one integration")
if manifest["domain"] != component.name or not manifest.get("config_flow"):
    errors.append("Domain/config flow mismatch")
if manifest.get("requirements") != [] or manifest.get("iot_class") != "local_polling":
    errors.append("Unexpected runtime dependency or I/O class")
if hacs.get("homeassistant") != "2026.11.0":
    errors.append("Review and test any changed Home Assistant minimum")
if hacs.get("name") != manifest["name"]:
    errors.append("HACS and Home Assistant display names differ")


def translation_entries(catalog, path=()):
    for key, value in catalog.items():
        if isinstance(value, dict):
            yield from translation_entries(value, (*path, key))
        else:
            yield (*path, key), value


def placeholders(message):
    return Counter(field for _, field, _, _ in Formatter().parse(message) if field is not None)


async def check_loaded_translations(config_dir, catalogs):
    hass = HomeAssistant(config_dir)
    loader.async_setup(hass)
    for language, catalog in catalogs.items():
        for category in catalog:
            actual = await async_get_translations(hass, language, category, {component.name})
            expected = {
                ".".join(("component", component.name, *path)): value
                for path, value in translation_entries({category: catalog[category]})
            }
            if actual != expected:
                errors.append(f"Home Assistant loaded different texts: {language}/{category}")


languages = ("nl", "en", "de", "fr", "it")
strings = json.loads((component / "strings.json").read_text(encoding="utf-8"))
original = dict(translation_entries(strings))
catalogs = {}
for lang in languages:
    translated = json.loads((component / f"translations/{lang}.json").read_text(encoding="utf-8"))
    catalogs[lang] = translated
    if translated.get("title") != manifest["name"]:
        errors.append(f"Integration display name differs: {lang}")
    entries = dict(translation_entries(translated))
    if entries.keys() != original.keys():
        errors.append(f"Translation keys differ: {lang}")
        continue
    for path, message in entries.items():
        if not isinstance(message, str) or not message.strip():
            errors.append(f"Empty or invalid text: {lang}/{'/'.join(path)}")
        elif placeholders(message) != placeholders(original[path]):
            errors.append(f"Translation placeholders differ: {lang}/{'/'.join(path)}")
if not errors:
    with TemporaryDirectory() as config_dir:
        target = Path(config_dir) / "custom_components" / component.name
        target.mkdir(parents=True)
        shutil.copyfile(component / "manifest.json", target / "manifest.json")
        shutil.copytree(component / "translations", target / "translations")
        asyncio.run(check_loaded_translations(config_dir, catalogs))
if not errors:
    print(f"Translations: {', '.join(languages)} ({len(original)} texts each), loaded by HA Core")
for name, expected in (("icon.png", (256, 256)), ("icon@2x.png", (512, 512))):
    with Image.open(component / "brand" / name) as icon:
        if icon.size != expected or icon.mode != "RGBA":
            errors.append(f"Invalid brand image: {name}")
if not manifest.get("codeowners") or any(
    not re.fullmatch(r"@[A-Za-z0-9-]+", owner) for owner in manifest["codeowners"]
):
    pending.append("Confirm GitHub owner and fill manifest codeowners")
if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/issues", manifest.get("issue_tracker", "")):
    pending.append("Set the actual GitHub issue tracker after repository creation")
for name in (
    "README.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "RELEASE.md",
    "custom_components/viega_fonterra_modbus/LICENSE",
):
    if not (root / name).is_file():
        errors.append(f"Missing {name}")
for error in errors:
    print(f"ERROR: {error}")
for item in pending:
    print(f"PUBLICATION PENDING: {item}")
print("Candidate structure: " + ("PASS" if not errors else "FAIL"))
if not args.candidate and pending:
    print("Release: BLOCKED by the publication items above")
sys.exit(bool(errors or (pending and not args.candidate)))
