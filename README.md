# Viega Fonterra Smart

[Nederlands](#nederlands) · [For English, see below](#english) · [Auf Deutsch weiterlesen](#deutsch)

## Nederlands

Regel je Viega Fonterra Smart Control-vloerverwarming vanuit Home Assistant. De integratie vindt je verdelers en leest de kamerindeling uit Fonterra. Je ziet per ruimte de gemeten en ingestelde temperatuur, plus de aanvoertemperatuur, pompstatus en diagnose van de basisunit. Met [Connected Upgrade van Gigaweb](https://www.gigaweb.nl/fonterra-smart-control-upgrade/) kun je hiervoor ook een eigen temperatuursensor gebruiken.

**Inhoud**

- [Vereisten](#vereisten)
- [Installeren](#installeren)
- [Dashboardkaart](#dashboardkaart)
- [Je eigen temperatuursensor](#je-eigen-temperatuursensor)
- [Kamers en verbinding](#kamers-en-verbinding)
- [Hulp en ontwikkeling](#hulp-en-ontwikkeling)

### Vereisten

Home Assistant 2026.11.0 of nieuwer. Schakel Modbus TCP in Fonterra in en zorg dat Home Assistant de verdeler op poort 502 kan bereiken.

### Installeren

1. [Open Viega Fonterra Smart in de Marketplace](https://my.home-assistant.io/redirect/marketplace_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration). Je kunt ook onder **Instellingen > Marketplace > Toevoegen via link** de GitHub-repository invoeren.
2. Open **Viega Fonterra Smart** in de Marketplace en kies **Installeren**. Herstart Home Assistant als daarom wordt gevraagd.
3. Open **Instellingen > Apparaten & diensten** en bevestig de gevonden verdeler. Je kunt **Viega Fonterra Smart** ook toevoegen met het IP-adres of de hostnaam. Elke verdeler krijgt een eigen vermelding.

Voor een handmatige installatie pak je de ZIP van de [GitHub-release](https://github.com/roelbroersma/viega-fonterra-smart-control/releases/latest) uit. Kopieer `custom_components/viega_fonterra_modbus` naar de gelijknamige map in je Home Assistant-configuratie en herstart.

### Dashboardkaart

Vernieuw je browser na de herstart. Kies **Dashboard bewerken > Kaart toevoegen > Viega Fonterra Smart**. Gebruik het overzicht voor alle ruimtes of kies één kamer. Stel de doeltemperatuur bij of wijzig de vermogensstand bij een losse groep die deze bediening ondersteunt. Een kamerfout verschijnt onder **Diagnose**, op basis van de foutcode van Fonterra.

![Vloerverwarmingsoverzicht en ruimtekaart voor de badkamer](docs/dashboard.png)

Gebruik deze YAML voor een ruimtekaart.

```yaml
type: custom:viega-fonterra-card
entity: climate.voorbeeld_badkamer
```

Vervang de entiteit door je eigen klimaatentiteit. Laat `entity` weg voor het overzicht.

### Je eigen temperatuursensor

Stel dat `sensor.badkamer_temperatuur` in Home Assistant de temperatuur van een KNX Tastsensor 4 ontvangt.

1. Kies voor de badkamer in Fonterra **Extern gemeten**. Deze optie is beschikbaar met [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/).
2. Open **Configureren** bij de verdeler in Home Assistant. Vink **Connect Upgrade geïnstalleerd** aan en kies **Badkamer** bij **Kamersensor koppelen (optioneel)**.
3. Selecteer `sensor.badkamer_temperatuur`, bevestig de externe bron en sla op. Controleer de gemeten temperatuur in Fonterra. Een meting van **21,8 °C** gaat naar de gemeten temperatuur. De gewenste temperatuur stel je afzonderlijk in.

Als je de KNX-sensor in YAML aanmaakt, gebruik dan je eigen groepsadres. De sensor moet leesverzoeken kunnen beantwoorden.

```yaml
knx:
  sensor:
    - name: Badkamer temperatuur
      state_address: "1/2/3"
      type: temperature
      always_callback: true
      sync_state: "expire 5"
```

`always_callback` verwerkt ook een gelijke meting. `sync_state` vraagt na vijf minuten zonder telegram een waarde op. Home Assistant stopt met doorgeven als de bron onbeschikbaar is of de meting te oud wordt. Fonterra bepaalt wanneer de ontvangen temperatuur verloopt en meldt een kamerfout via **Diagnose**.

### Kamers en verbinding

Wijzig kamernamen en de actorindeling in Fonterra. Kies daarna **Herladen** of gebruik **Ruimten opnieuw ontdekken** in Home Assistant. Verwarmen, koelen en stand-by gelden voor de hele basisunit.

Home Assistant controleert het WLAN-serienummer voordat het bij een bekende verdeler een nieuw adres overneemt. Je kunt het adres ook handmatig aanpassen bij **Configureren**.

### Hulp en ontwikkeling

De kaart en integratie volgen de taal van Home Assistant. Nederlands, Engels, Duits, Frans en Italiaans zijn beschikbaar. Meld problemen via [GitHub Issues](https://github.com/roelbroersma/viega-fonterra-smart-control/issues) met je Home Assistant-versie en de relevante foutmelding.

[Tests, bouwen en release-informatie](RELEASE.md) · [Bronnen en licenties](THIRD_PARTY_NOTICES.md)

## English

Control your Viega Fonterra Smart Control underfloor heating from Home Assistant. The integration discovers your controllers and reads the room layout from Fonterra. You can see each room’s measured temperature and setpoint, along with the supply temperature, pump status and controller diagnostics. With [Gigaweb Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/), you can use your own temperature sensor.

**Contents**

- [Requirements](#requirements)
- [Installation](#installation)
- [Dashboard card](#dashboard-card)
- [Using your own temperature sensor](#using-your-own-temperature-sensor)
- [Rooms and connectivity](#rooms-and-connectivity)
- [Help and development](#help-and-development)

### Requirements

Home Assistant 2026.11.0 or later. Enable Modbus TCP in Fonterra and make sure Home Assistant can reach the controller on port 502.

### Installation

1. [Open Viega Fonterra Smart in the Marketplace](https://my.home-assistant.io/redirect/marketplace_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration). You can also enter the GitHub repository under **Settings > Marketplace > Add from link**.
2. Open **Viega Fonterra Smart** in the Marketplace and choose **Install**. Restart Home Assistant if prompted.
3. Go to **Settings > Devices & services** and confirm the discovered controller. You can also add **Viega Fonterra Smart** using the IP address or hostname. Each controller has its own entry.

For manual installation, extract the ZIP from the [GitHub release](https://github.com/roelbroersma/viega-fonterra-smart-control/releases/latest). Copy `custom_components/viega_fonterra_modbus` to the matching folder in your Home Assistant configuration and restart.

### Dashboard card

Refresh your browser after restarting. Go to **Edit dashboard > Add card > Viega Fonterra Smart**. Use the overview for all rooms or select a single room. Adjust the setpoint or change the power level for a standalone group that supports it. Room faults appear under **Diagnostics**, based on the code reported by Fonterra. [View the dashboard screenshot](docs/dashboard.png)

Use this YAML to add a room card.

```yaml
type: custom:viega-fonterra-card
entity: climate.example_bathroom
```

Replace the example with your climate entity. Omit `entity` for the overview.

### Using your own temperature sensor

Suppose `sensor.bathroom_temperature` in Home Assistant receives readings from a KNX Tastsensor 4.

1. In Fonterra, select **External measured** for the bathroom. This option is available with [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/).
2. Open **Configure** on the controller in Home Assistant. Tick **Connect Upgrade installed** and select **Bathroom** under **Room sensor (optional)**.
3. Select `sensor.bathroom_temperature`, confirm the external source and save. Check the reading in Fonterra. A reading of **21.8 °C** is sent as the measured temperature. The setpoint is set separately.

When setting up the KNX sensor in YAML, use your own group address. The sensor must respond to read requests.

```yaml
knx:
  sensor:
    - name: Bathroom temperature
      state_address: "1/2/3"
      type: temperature
      always_callback: true
      sync_state: "expire 5"
```

`always_callback` also processes identical readings. `sync_state` requests a value after five minutes without a telegram. Home Assistant stops sending when the source is unavailable or the reading is too old. Fonterra decides when the last received reading expires and reports room faults under **Diagnostics**.

### Rooms and connectivity

Change room names and actuator assignments in Fonterra. Then **Reload** the integration entry or use the **Rediscover rooms** action in Home Assistant. Heating, cooling and standby apply to the entire base unit.

Home Assistant verifies the Wi-Fi module serial before adopting a new address for a known controller. You can also change the address manually under **Configure**.

### Help and development

The card and integration follow your Home Assistant language. Dutch, English, German, French and Italian are available. Report problems via [GitHub Issues](https://github.com/roelbroersma/viega-fonterra-smart-control/issues) with your Home Assistant version and the relevant error.

[Tests, build instructions and release information](RELEASE.md) · [Sources and licenses](THIRD_PARTY_NOTICES.md)

## Deutsch

Steuern Sie Ihre Viega Fonterra Smart-Control-Fußbodenheizung in Home Assistant. Die Integration findet Ihre Verteiler und liest die Raumaufteilung aus Fonterra aus. Sie sehen die gemessene Temperatur und die Solltemperatur pro Raum sowie Vorlauftemperatur, Pumpenstatus und Diagnose der Basiseinheit. Mit dem [Connected Upgrade von Gigaweb](https://www.gigaweb.nl/fonterra-smart-control-upgrade/) können Sie einen eigenen Temperatursensor verwenden.

**Inhalt**

- [Voraussetzungen](#voraussetzungen)
- [Installation](#inbetriebnahme)
- [Dashboard-Karte](#dashboard-karte)
- [Eigenen Temperatursensor verwenden](#eigenen-temperatursensor-verwenden)
- [Räume und Verbindung](#räume-und-verbindung)
- [Hilfe und Entwicklung](#hilfe-und-entwicklung)

### Voraussetzungen

Home Assistant 2026.11.0 oder neuer. Aktivieren Sie Modbus TCP in Fonterra. Home Assistant muss den Verteiler über Port 502 erreichen können.

### Inbetriebnahme

1. [Viega Fonterra Smart im Marketplace öffnen](https://my.home-assistant.io/redirect/marketplace_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration). Sie können das GitHub-Repository auch unter **Einstellungen > Marketplace > Per Link hinzufügen** eingeben.
2. Öffnen Sie **Viega Fonterra Smart** im Marketplace und wählen Sie **Installieren**. Starten Sie Home Assistant neu, wenn Sie dazu aufgefordert werden.
3. Öffnen Sie **Einstellungen > Geräte & Dienste** und bestätigen Sie den gefundenen Verteiler. Sie können **Viega Fonterra Smart** auch über IP-Adresse oder Hostnamen hinzufügen. Jeder Verteiler erhält einen eigenen Eintrag.

Für die manuelle Installation entpacken Sie die ZIP-Datei aus dem [GitHub-Release](https://github.com/roelbroersma/viega-fonterra-smart-control/releases/latest). Kopieren Sie `custom_components/viega_fonterra_modbus` in den gleichnamigen Ordner Ihrer Home-Assistant-Konfiguration und starten Sie Home Assistant neu.

### Dashboard-Karte

Laden Sie die Browserseite nach dem Neustart neu. Wählen Sie **Dashboard bearbeiten > Karte hinzufügen > Viega Fonterra Smart**. Verwenden Sie die Übersicht für alle Räume oder wählen Sie einen einzelnen Raum. Stellen Sie die Solltemperatur ein oder ändern Sie die Leistungsstufe einer einzelnen Heizgruppe, sofern diese Funktion verfügbar ist. Raumfehler erscheinen unter **Diagnose** mit der von Fonterra gemeldeten Störung. [Dashboard ansehen](docs/dashboard.png)

Mit diesem YAML-Beispiel fügen Sie eine Raumkarte hinzu.

```yaml
type: custom:viega-fonterra-card
entity: climate.beispiel_badezimmer
```

Ersetzen Sie das Beispiel durch Ihre Klimaentität. Lassen Sie `entity` für die Übersicht weg.

### Eigenen Temperatursensor verwenden

Angenommen, `sensor.badezimmertemperatur` in Home Assistant erhält Messwerte von einem KNX Tastsensor 4.

1. Wählen Sie für das Badezimmer in Fonterra die externe Messung (**Extern gemessen**). Diese Option ist mit dem [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/) verfügbar.
2. Öffnen Sie in Home Assistant **Konfigurieren** beim Verteiler. Aktivieren Sie **Connect Upgrade installiert** und wählen Sie **Badezimmer** unter **Raumsensor verknüpfen (optional)**.
3. Wählen Sie `sensor.badezimmertemperatur`, bestätigen Sie die externe Messquelle und speichern Sie. Prüfen Sie die gemessene Temperatur in Fonterra. Ein Messwert von **21,8 °C** wird als gemessene Raumtemperatur übertragen. Die Solltemperatur stellen Sie separat ein.

Wenn Sie den KNX-Sensor in YAML einrichten, verwenden Sie Ihre eigene Gruppenadresse. Der Sensor muss auf Leseanfragen antworten.

```yaml
knx:
  sensor:
    - name: Badezimmertemperatur
      state_address: "1/2/3"
      type: temperature
      always_callback: true
      sync_state: "expire 5"
```

`always_callback` verarbeitet auch identische Messwerte. `sync_state` fordert nach fünf Minuten ohne Telegramm einen Messwert an. Home Assistant stellt die Übertragung ein, wenn der Sensor nicht verfügbar oder der Messwert zu alt ist. Fonterra bestimmt, wann der letzte Messwert abläuft, und meldet Raumfehler unter **Diagnose**.

### Räume und Verbindung

Ändern Sie Raumnamen und Stellantriebszuordnung in Fonterra. Wählen Sie anschließend in Home Assistant **Neu laden** oder führen Sie die Aktion **Räume erneut erkennen** aus. Heizen, Kühlen und Stand-by gelten für die gesamte Basiseinheit.

Home Assistant prüft die Seriennummer des WLAN-Moduls, bevor es eine neue Adresse für einen bekannten Verteiler übernimmt. Sie können die Adresse auch unter **Konfigurieren** manuell ändern.

### Hilfe und Entwicklung

Karte und Integration folgen der Spracheinstellung von Home Assistant. Niederländisch, Englisch, Deutsch, Französisch und Italienisch sind verfügbar. Melden Sie Probleme über [GitHub Issues](https://github.com/roelbroersma/viega-fonterra-smart-control/issues) und geben Sie Ihre Home-Assistant-Version und die relevante Fehlermeldung an.

[Tests, Build-Anleitung und Release-Informationen](RELEASE.md) · [Quellen und Lizenzen](THIRD_PARTY_NOTICES.md)
