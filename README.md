# Viega Fonterra Smart

[Nederlands](https://github.com/roelbroersma/viega-fonterra-smart-control#nederlands) · [For English, see below](https://github.com/roelbroersma/viega-fonterra-smart-control#english) · [Auf Deutsch weiterlesen](https://github.com/roelbroersma/viega-fonterra-smart-control#deutsch)

## Nederlands

Regel je Viega Fonterra Smart Control-vloerverwarming vanuit Home Assistant. De integratie vindt je verdelers via het netwerk en leest de kamerindeling uit. De dashboardkaart toont temperaturen, klepstanden en diagnose en laat je de ruimtetemperatuur instellen.

Met [Connected Upgrade van Gigaweb](https://www.gigaweb.nl/fonterra-smart-control-upgrade/) kun je per kamer de meting van een Home Assistant-sensor doorgeven, bijvoorbeeld van een KNX-tastsensor. Fonterra gebruikt die meting om de kamer te regelen. Voor de gewone bediening via Modbus TCP is de upgrade optioneel.

**Inhoud**

- [Vereisten](https://github.com/roelbroersma/viega-fonterra-smart-control#vereisten)
- [Installeren](https://github.com/roelbroersma/viega-fonterra-smart-control#installeren)
- [Dashboardkaart](https://github.com/roelbroersma/viega-fonterra-smart-control#dashboardkaart)
- [Je eigen temperatuursensor](https://github.com/roelbroersma/viega-fonterra-smart-control#je-eigen-temperatuursensor)
- [Kamers en verbinding](https://github.com/roelbroersma/viega-fonterra-smart-control#kamers-en-verbinding)
- [Hulp en ontwikkeling](https://github.com/roelbroersma/viega-fonterra-smart-control#hulp-en-ontwikkeling)

### Vereisten

Home Assistant 2026.11.0 of nieuwer. Schakel Modbus TCP in Fonterra in en zorg dat Home Assistant de verdeler op poort 502 kan bereiken.

### Installeren

1. Zoek naar **Viega Fonterra Smart** onder **Instellingen > Marketplace**. Zie je hem nog niet? [Open de integratie via deze link](https://my.home-assistant.io/redirect/marketplace_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration). Je kunt de GitHub-repository ook invoeren via **Voeg toe via link**.
2. Open **Viega Fonterra Smart** in de Marketplace en kies **Installeren**. Herstart Home Assistant als daarom wordt gevraagd.
3. Open **Instellingen > Apparaten & diensten** en bevestig de gevonden verdeler. Je kunt **Viega Fonterra Smart** ook toevoegen met het IP-adres of de hostnaam. Elke verdeler krijgt een eigen vermelding.

Voor een handmatige installatie pak je de ZIP van de [GitHub-release](https://github.com/roelbroersma/viega-fonterra-smart-control/releases/latest) uit. Kopieer `custom_components/viega_fonterra_modbus` naar de gelijknamige map in je Home Assistant-configuratie en herstart.

### Dashboardkaart

Vernieuw je browser na de herstart. Kies **Dashboard bewerken > Kaart toevoegen > Viega Fonterra Smart**. Gebruik het overzicht voor alle ruimtes of kies één kamer. Stel de doeltemperatuur bij of wijzig de vermogensstand voor een losse actor die deze bediening ondersteunt. Per actor zie je de klepstand en retourtemperatuur. Een kamerfout verschijnt onder **Diagnose**, op basis van de foutcode van Fonterra.

![Vloerverwarmingsoverzicht en ruimtekaart voor de badkamer](docs/dashboard.png)

Gebruik deze YAML voor een ruimtekaart.

```yaml
type: custom:viega-fonterra-card
entity: climate.voorbeeld_badkamer
```

Vervang de entiteit door je eigen klimaatentiteit. Laat `entity` weg voor het overzicht.

#### Geschiedenis per ruimte

Voeg onder de ruimtekaart een **Geschiedenisgrafiek** toe en selecteer de Fonterra-klimaatentiteit van de kamer. Home Assistant toont de gemeten en ingestelde temperatuur en markeert de periodes waarin de kamer verwarmt. De grafiek gebruikt de geschiedenis die Home Assistant heeft opgeslagen.

```yaml
type: history-graph
title: Badkamer
hours_to_show: 24
entities:
  - climate.voorbeeld_badkamer
```

Kopieer de kaart voor elke ruimte en vervang de titel en de klimaatentiteit.

### Je eigen temperatuursensor

1. Zet de ruimte in Fonterra op **Extern gemeten**. Dit kan met de [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/).
2. Vink **Connect Upgrade geïnstalleerd** aan onder **Configureren** in Home Assistant en sla op.
3. Open de entiteiten van de verdeler. Zoek onder de uitgeschakelde entiteiten naar **Badkamer externe temperatuurinvoer** en schakel die in. Herhaal dit voor iedere ruimte die je extern meet.

Test de invoer met een actuele meting. Gebruik daarna de actie **Getal instellen** in een automatisering. Dit voorbeeld stuurt elke minuut de waarde van een temperatuursensor in °C, zolang die in de afgelopen tien minuten een meting heeft gemeld. Vervang de twee entiteits-ID's door die van jouw installatie.

```yaml
alias: Badkamer temperatuur doorgeven
triggers:
  - trigger: time_pattern
    minutes: "/1"
conditions:
  - condition: template
    value_template: >
      {{ is_number(states('sensor.badkamer_temperatuur'))
          and as_timestamp(now()) - as_timestamp(states.sensor.badkamer_temperatuur.last_reported, 0) < 600 }}
actions:
  - action: number.set_value
    target:
      entity_id: number.fonterra_badkamer_externe_temperatuurinvoer
    data:
      value: "{{ states('sensor.badkamer_temperatuur') | float }}"
```

Laat je sensor ook bij een gelijkblijvende temperatuur metingen melden. Voor KNX kun je daarvoor bijvoorbeeld de sensor laten antwoorden op leesverzoeken en `always_callback` en `sync_state` instellen. De invoer stuurt per aanroep één meting. De gewenste temperatuur stel je in via de thermostaatkaart.

Had je al een sensor gekoppeld via de integratie? Die blijft werken totdat je de invoer voor die ruimte inschakelt. Zet daarvoor eerst je automatisering klaar. Schakel je de invoer later uit, dan stopt het doorgeven voor die ruimte.

### Kamers en verbinding

Wijzig kamernamen en de actorindeling in Fonterra. Kies daarna **Herladen** of gebruik **Ruimten opnieuw ontdekken** in Home Assistant. Verwarmen, koelen en stand-by gelden voor de hele basisunit.

Home Assistant controleert het WLAN-serienummer voordat het bij een bekende verdeler een nieuw adres overneemt. Je kunt het adres ook handmatig aanpassen bij **Configureren**.

### Hulp en ontwikkeling

De kaart en integratie volgen de taal van Home Assistant. Nederlands, Engels, Duits, Frans en Italiaans zijn beschikbaar. Meld problemen via [GitHub Issues](https://github.com/roelbroersma/viega-fonterra-smart-control/issues) met je Home Assistant-versie en de relevante foutmelding.

[Tests, bouwen en release-informatie](RELEASE.md) · [Bronnen en licenties](THIRD_PARTY_NOTICES.md)

## English

Control your Viega Fonterra Smart Control underfloor heating from Home Assistant. The integration discovers your controllers on the network and reads the room layout. The dashboard card shows temperatures, valve positions and diagnostics and lets you adjust the room setpoint.

With [Gigaweb Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/), you can send readings from a Home Assistant sensor, such as a KNX wall sensor, to Fonterra for each room. Fonterra uses those readings to control the room. The upgrade is optional for standard Modbus TCP control.

**Contents**

- [Requirements](https://github.com/roelbroersma/viega-fonterra-smart-control#requirements)
- [Installation](https://github.com/roelbroersma/viega-fonterra-smart-control#installation)
- [Dashboard card](https://github.com/roelbroersma/viega-fonterra-smart-control#dashboard-card)
- [Using your own temperature sensor](https://github.com/roelbroersma/viega-fonterra-smart-control#using-your-own-temperature-sensor)
- [Rooms and connectivity](https://github.com/roelbroersma/viega-fonterra-smart-control#rooms-and-connectivity)
- [Help and development](https://github.com/roelbroersma/viega-fonterra-smart-control#help-and-development)

### Requirements

Home Assistant 2026.11.0 or later. Enable Modbus TCP in Fonterra and make sure Home Assistant can reach the controller on port 502.

### Installation

1. Search for **Viega Fonterra Smart** under **Settings > Marketplace**. If it does not appear, [open the integration from this link](https://my.home-assistant.io/redirect/marketplace_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration). You can also enter the GitHub repository under **Settings > Marketplace > Add from link**.
2. Open **Viega Fonterra Smart** in the Marketplace and choose **Install**. Restart Home Assistant if prompted.
3. Go to **Settings > Devices & services** and confirm the discovered controller. You can also add **Viega Fonterra Smart** using the IP address or hostname. Each controller has its own entry.

For manual installation, extract the ZIP from the [GitHub release](https://github.com/roelbroersma/viega-fonterra-smart-control/releases/latest). Copy `custom_components/viega_fonterra_modbus` to the matching folder in your Home Assistant configuration and restart.

### Dashboard card

Refresh your browser after restarting. Go to **Edit dashboard > Add card > Viega Fonterra Smart**. Use the overview for all rooms or select a single room. Adjust the setpoint or change the power level for a standalone actuator that supports it. The card shows the valve position and return temperature for each actuator. Room faults appear under **Diagnostics**, based on the code reported by Fonterra. [View the dashboard screenshot](docs/dashboard.png)

Use this YAML to add a room card.

```yaml
type: custom:viega-fonterra-card
entity: climate.example_bathroom
```

Replace the example with your climate entity. Omit `entity` for the overview.

#### Room history

Add a **History graph** below the room card and select the Fonterra climate entity for that room. Home Assistant shows the measured temperature, the setpoint and the periods when the room was heating. The graph uses the history recorded by Home Assistant.

```yaml
type: history-graph
title: Bathroom
hours_to_show: 24
entities:
  - climate.example_bathroom
```

Duplicate the card for each room and change its title and climate entity.

### Using your own temperature sensor

1. Set the room to **External measured** in Fonterra. This option is available with the [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/).
2. Under **Configure** in Home Assistant, tick **Connect Upgrade installed** and save.
3. Open the controller's entities. Find **Bathroom external temperature input** among the disabled entities and enable it. Repeat for each room you measure externally.

Test the input with a current reading, then use **Set value** in an automation. This example sends a reading in °C once per minute if the sensor has reported within the last ten minutes. Replace both entity IDs with your own.

```yaml
alias: Send bathroom temperature
triggers:
  - trigger: time_pattern
    minutes: "/1"
conditions:
  - condition: template
    value_template: >
      {{ is_number(states('sensor.bathroom_temperature'))
          and as_timestamp(now()) - as_timestamp(states.sensor.bathroom_temperature.last_reported, 0) < 600 }}
actions:
  - action: number.set_value
    target:
      entity_id: number.fonterra_bathroom_external_temperature_input
    data:
      value: "{{ states('sensor.bathroom_temperature') | float }}"
```

Use a sensor that also reports when its value stays the same. For KNX, for example, configure the sensor to answer read requests and set `always_callback` and `sync_state`. Each action sends one reading. Set the target temperature on the thermostat card.

If you already linked a sensor through this integration, it keeps working until you enable the input for that room. Prepare your automation before enabling the input. Disabling the input later stops sending measurements for that room.

### Rooms and connectivity

Change room names and actuator assignments in Fonterra. Then **Reload** the integration entry or use the **Rediscover rooms** action in Home Assistant. Heating, cooling and standby apply to the entire base unit.

Home Assistant verifies the Wi-Fi module serial before adopting a new address for a known controller. You can also change the address manually under **Configure**.

### Help and development

The card and integration follow your Home Assistant language. Dutch, English, German, French and Italian are available. Report problems via [GitHub Issues](https://github.com/roelbroersma/viega-fonterra-smart-control/issues) with your Home Assistant version and the relevant error.

[Tests, build instructions and release information](RELEASE.md) · [Sources and licenses](THIRD_PARTY_NOTICES.md)

## Deutsch

Steuern Sie Ihre Viega Fonterra Smart-Control-Fußbodenheizung in Home Assistant. Die Integration findet Ihre Verteiler im Netzwerk und liest die Raumaufteilung aus. Die Dashboard-Karte zeigt Temperaturen, Ventilstellungen und Diagnose an. Dort können Sie auch die Solltemperatur einstellen.

Mit dem [Connected Upgrade von Gigaweb](https://www.gigaweb.nl/fonterra-smart-control-upgrade/) können Sie für jeden Raum Messwerte eines Home-Assistant-Sensors an Fonterra senden, zum Beispiel von einem KNX-Tastsensor. Fonterra regelt den Raum anhand dieser Messwerte. Für die normale Bedienung über Modbus TCP ist das Upgrade optional.

**Inhalt**

- [Voraussetzungen](https://github.com/roelbroersma/viega-fonterra-smart-control#voraussetzungen)
- [Installation](https://github.com/roelbroersma/viega-fonterra-smart-control#inbetriebnahme)
- [Dashboard-Karte](https://github.com/roelbroersma/viega-fonterra-smart-control#dashboard-karte)
- [Eigenen Temperatursensor verwenden](https://github.com/roelbroersma/viega-fonterra-smart-control#eigenen-temperatursensor-verwenden)
- [Räume und Verbindung](https://github.com/roelbroersma/viega-fonterra-smart-control#räume-und-verbindung)
- [Hilfe und Entwicklung](https://github.com/roelbroersma/viega-fonterra-smart-control#hilfe-und-entwicklung)

### Voraussetzungen

Home Assistant 2026.11.0 oder neuer. Aktivieren Sie Modbus TCP in Fonterra. Home Assistant muss den Verteiler über Port 502 erreichen können.

### Inbetriebnahme

1. Suchen Sie unter **Einstellungen > Marketplace** nach **Viega Fonterra Smart**. Falls der Eintrag fehlt, [öffnen Sie die Integration über diesen Link](https://my.home-assistant.io/redirect/marketplace_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration). Sie können das GitHub-Repository auch unter **Einstellungen > Marketplace > Per Link hinzufügen** eingeben.
2. Öffnen Sie **Viega Fonterra Smart** im Marketplace und wählen Sie **Installieren**. Starten Sie Home Assistant neu, wenn Sie dazu aufgefordert werden.
3. Öffnen Sie **Einstellungen > Geräte & Dienste** und bestätigen Sie den gefundenen Verteiler. Sie können **Viega Fonterra Smart** auch über IP-Adresse oder Hostnamen hinzufügen. Jeder Verteiler erhält einen eigenen Eintrag.

Für die manuelle Installation entpacken Sie die ZIP-Datei aus dem [GitHub-Release](https://github.com/roelbroersma/viega-fonterra-smart-control/releases/latest). Kopieren Sie `custom_components/viega_fonterra_modbus` in den gleichnamigen Ordner Ihrer Home-Assistant-Konfiguration und starten Sie Home Assistant neu.

### Dashboard-Karte

Laden Sie die Browserseite nach dem Neustart neu. Wählen Sie **Dashboard bearbeiten > Karte hinzufügen > Viega Fonterra Smart**. Verwenden Sie die Übersicht für alle Räume oder wählen Sie einen einzelnen Raum. Stellen Sie die Solltemperatur ein oder ändern Sie die Leistungsstufe eines einzelnen Stellantriebs, sofern diese Funktion verfügbar ist. Für jeden Stellantrieb zeigt die Karte die Ventilstellung und Rücklauftemperatur an. Raumfehler erscheinen unter **Diagnose** mit der von Fonterra gemeldeten Störung. [Dashboard ansehen](docs/dashboard.png)

Mit diesem YAML-Beispiel fügen Sie eine Raumkarte hinzu.

```yaml
type: custom:viega-fonterra-card
entity: climate.beispiel_badezimmer
```

Ersetzen Sie das Beispiel durch Ihre Klimaentität. Lassen Sie `entity` für die Übersicht weg.

#### Raumverlauf

Fügen Sie unter der Raumkarte ein **Verlaufsdiagramm** hinzu und wählen Sie die Fonterra-Klimaentität des Raums. Home Assistant zeigt die gemessene Temperatur, die Solltemperatur und die Zeiträume, in denen der Raum beheizt wurde. Das Diagramm verwendet den von Home Assistant aufgezeichneten Verlauf.

```yaml
type: history-graph
title: Badezimmer
hours_to_show: 24
entities:
  - climate.beispiel_badezimmer
```

Kopieren Sie die Karte für jeden Raum und ändern Sie den Titel und die Klimaentität.

### Eigenen Temperatursensor verwenden

1. Stellen Sie die Temperaturquelle des Raums in Fonterra auf **Extern gemessen**. Diese Option ist mit dem [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/) verfügbar.
2. Aktivieren Sie in Home Assistant unter **Konfigurieren** die Option **Connect Upgrade installiert** und speichern Sie.
3. Öffnen Sie die Entitäten des Verteilers. Suchen Sie unter den deaktivierten Entitäten nach **Badezimmer externe Temperatureingabe** und aktivieren Sie sie. Wiederholen Sie dies für jeden Raum mit externer Messung.

Testen Sie die Eingabe mit einem aktuellen Messwert und verwenden Sie anschließend die Aktion **Wert setzen** in einer Automation. Das Beispiel sendet jede Minute den Messwert in °C, sofern der Sensor in den letzten zehn Minuten gemeldet hat. Ersetzen Sie beide Entitäts-IDs durch Ihre eigenen.

```yaml
alias: Badezimmertemperatur übertragen
triggers:
  - trigger: time_pattern
    minutes: "/1"
conditions:
  - condition: template
    value_template: >
      {{ is_number(states('sensor.badezimmertemperatur'))
          and as_timestamp(now()) - as_timestamp(states.sensor.badezimmertemperatur.last_reported, 0) < 600 }}
actions:
  - action: number.set_value
    target:
      entity_id: number.fonterra_badezimmer_externe_temperatureingabe
    data:
      value: "{{ states('sensor.badezimmertemperatur') | float }}"
```

Der Sensor sollte auch bei unveränderter Temperatur Messwerte melden. Bei KNX kann der Sensor beispielsweise auf Leseanfragen antworten. Stellen Sie dafür `always_callback` und `sync_state` ein. Jeder Aufruf überträgt einen Messwert. Die Solltemperatur stellen Sie auf der Thermostatkarte ein.

Eine bereits in der Integration eingerichtete Sensorverknüpfung bleibt aktiv, bis Sie die Eingabe für den Raum einschalten. Bereiten Sie vorher die Automation vor. Wenn Sie die Eingabe später deaktivieren, endet die Übertragung für diesen Raum.

### Räume und Verbindung

Ändern Sie Raumnamen und Stellantriebszuordnung in Fonterra. Wählen Sie anschließend in Home Assistant **Neu laden** oder führen Sie die Aktion **Räume erneut erkennen** aus. Heizen, Kühlen und Stand-by gelten für die gesamte Basiseinheit.

Home Assistant prüft die Seriennummer des WLAN-Moduls, bevor es eine neue Adresse für einen bekannten Verteiler übernimmt. Sie können die Adresse auch unter **Konfigurieren** manuell ändern.

### Hilfe und Entwicklung

Karte und Integration folgen der Spracheinstellung von Home Assistant. Niederländisch, Englisch, Deutsch, Französisch und Italienisch sind verfügbar. Melden Sie Probleme über [GitHub Issues](https://github.com/roelbroersma/viega-fonterra-smart-control/issues) und geben Sie Ihre Home-Assistant-Version und die relevante Fehlermeldung an.

[Tests, Build-Anleitung und Release-Informationen](RELEASE.md) · [Quellen und Lizenzen](THIRD_PARTY_NOTICES.md)
