# Release en onderhoud

## Waar staat wat?

- `room_mapping.py` leest de actorindeling en kamernamen. `registers.py` bewaart de registeradressen en vertaalbare diagnosecodes.
- `rediscovery.py` werkt de actieve kamerentiteiten bij, inclusief de externe temperatuurinvoer. Na een lege uitlezing blijft de laatst bekende kamerindeling beschikbaar.
- `coordinator.py` verzamelt registerwaarden per verdeler. Klimaatentiteiten, sensoren en diagnose delen dit resultaat.
- `connect/number.py` biedt na inschakelen van Connect Upgrade per ruimte een standaard uitgeschakelde temperatuurinvoer. `connect/coordinator.py` controleert de WLAN-identiteit en de huidige actortoewijzing vóór het schrijven. Een ingestelde waarde wordt één keer verstuurd. Een bestaande automatische sensorkoppeling blijft actief zolang de invoer voor die ruimte op de standaardinstelling staat.
- `card/` toont de bestaande entiteiten. De kaart vraagt temperatuur- en vermogenswijzigingen via normale Home Assistant-acties aan.
- `docs/modbus_contract.json` legt het gebruikte registercontract vast.

## Testen en verpakken

Gebruik Python **3.14.10**, uv **0.13.8**, Node.js **26.11.1** en npm **11.20.0**. Voer de opdrachten uit in de projectmap. Gebruik op Linux of macOS `.venv/bin/python` en laat de PowerShell-operator `&` weg.

```powershell
uv venv --python 3.14.10 .venv
uv pip sync --index-url https://pypi.org/simple --python .venv/Scripts/python.exe --require-hashes requirements/ha-2026.11.1.lock.txt
& .venv/Scripts/python.exe -m ruff check .
& .venv/Scripts/python.exe -m ruff format --check .
& .venv/Scripts/python.exe -m pytest -q
& .venv/Scripts/python.exe scripts/check_release.py
node --test tests/test_card.mjs
npm --prefix tests/browser ci
npm --prefix tests/browser run install-browser
npm --prefix tests/browser test
& .venv/Scripts/python.exe scripts/build_candidate.py
```

Gebruik `requirements/ha-2026.11.0.lock.txt` om ook de minimale Home Assistant-versie te testen. De browsertest gebruikt Playwright **1.65.1**. Stel `FONTERRA_CHROMIUM_PATH` in als je een bestaande Chrome- of Chromium-installatie wilt gebruiken. Het bouwscript schrijft de ZIP en checksum naar `outputs/`. Hetzelfde bronarchief levert bij opnieuw bouwen dezelfde SHA-256.

Voor de lokale hassfest-controle gebruik je Home Assistant Core **2026.11.1**, commit `d8a0dc698c8946b44e455d904000db563cfbf1ba`.

```powershell
git clone --depth 1 --branch 2026.11.1 --filter=blob:none --sparse https://github.com/home-assistant/core.git ../fonterra-ha-core-2026.11.1
git -C ../fonterra-ha-core-2026.11.1 sparse-checkout set packages/hassfest script/hassfest
$fonterraCore = (Resolve-Path ../fonterra-ha-core-2026.11.1).Path
$env:PYTHONPATH = $fonterraCore + [IO.Path]::PathSeparator + (Join-Path $fonterraCore packages/hassfest)
& .venv/Scripts/python.exe -m script.hassfest --integration-path ./custom_components/viega_fonterra_modbus --core-path $fonterraCore
Remove-Item Env:PYTHONPATH
```
