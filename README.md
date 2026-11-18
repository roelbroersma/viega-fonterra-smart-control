# Viega Fonterra Smart voor Home Assistant

Bekijk en regel je Viega Fonterra Smart Control-vloerverwarming vanaf je dashboard. De integratie vindt je verdelers en leest de kamerindeling uit Fonterra. Je ziet de actuele en ingestelde temperatuur per ruimte, de aanvoertemperatuur, de pompstatus en de diagnose van de basisunit.

Ook geschikt voor [Connected Upgrade van Gigaweb](https://www.gigaweb.nl/fonterra-smart-control-upgrade/). Laat Fonterra regelen met de temperatuur van een sensor die je al in Home Assistant hebt.

**Vereisten** · Home Assistant 2026.11.0 of nieuwer · Modbus TCP ingeschakeld in Fonterra · Home Assistant kan de verdeler bereiken op poort 502.

## Installeren

1. Open [Viega Fonterra Smart in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration). Je kunt de GitHub-repository ook zelf toevoegen via **HACS > ⋮ > Aangepaste repositories**, type **Integratie**.
2. Download de integratie en herstart Home Assistant.
3. Open **Instellingen > Apparaten & diensten** en bevestig de gevonden verdeler. Je kunt **Viega Fonterra Smart** ook toevoegen met het IP-adres of de hostnaam. Elke verdeler krijgt een eigen vermelding.

Voor een handmatige installatie pak je de ZIP van de [GitHub-release](https://github.com/roelbroersma/viega-fonterra-smart-control/releases/latest) uit. Kopieer `custom_components/viega_fonterra_modbus` naar de gelijknamige map in je Home Assistant-configuratie en herstart Home Assistant.

Draai je een eerdere testversie uit de 1.4.0-rc-reeks? Selecteer **0.9.0** expliciet bij het downloaden of vervang de integratiemap handmatig. Laat de bestaande integratievermelding in **Apparaten & diensten** staan, zodat je instellingen en klimaatentiteiten behouden blijven. Gebruik één bron voor de integratie, ook als je eerder de communityversie gebruikte.

## Dashboardkaart

Vernieuw je browser na de herstart. Open **Dashboard bewerken > Kaart toevoegen** en kies **Viega Fonterra Smart**. Kies alle ruimtes of één kamer. Op een losse groep kun je de beschikbare vermogensstand instellen. Met een thermostaat stel je de doeltemperatuur in.

![Viega Fonterra Smart met een vloerverwarmingsoverzicht en de kaart voor de badkamer](docs/dashboard.png)

Wil je de kaart in YAML toevoegen?

```yaml
type: custom:viega-fonterra-card
entity: climate.voorbeeld_badkamer
```

Vervang de entiteit door je eigen klimaatentiteit. Laat `entity` weg voor het overzicht.

## Voorbeeld · je eigen temperatuursensor in de badkamer

Je hebt bijvoorbeeld al `sensor.badkamer_temperatuur`, gemeten door een KNX Tastsensor 4.

1. Kies in Fonterra voor de badkamer **Extern gemeten**. Deze optie is beschikbaar met [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/).
2. Open bij de verdeler in Home Assistant **Configureren > Connect Upgrade**. Vink aan dat de upgrade is geïnstalleerd, kies **Badkamer** en selecteer `sensor.badkamer_temperatuur`. Bevestig de externe bron.
3. Controleer de gemeten temperatuur in Fonterra. Een sensormeting van **21,8 °C** wordt als gemeten temperatuur doorgegeven. De gewenste temperatuur stel je apart in.

Voor een KNX-sensor in YAML kan dit er zo uitzien. Gebruik het groepsadres van je eigen temperatuurmeting. De sensor moet leesverzoeken kunnen beantwoorden.

```yaml
knx:
  sensor:
    - name: Badkamer temperatuur
      state_address: "1/2/3"
      type: temperature
      always_callback: true
      sync_state: "expire 5"
```

`always_callback` verwerkt ook een gelijke meting. `sync_state` vraagt na vijf minuten zonder telegram een waarde op. Zorg dat je sensor regelmatig een echte meting meldt. Home Assistant stopt met doorgeven als de bron onbeschikbaar is of de meting te oud wordt. Fonterra bepaalt wanneer een eerder ontvangen waarde verloopt en meldt een kamerfout via **Diagnose**.

## Kamers, verbinding en hulp

Pas kamernamen en de actorindeling aan in Fonterra. Kies daarna **Herladen** of gebruik **Ruimten opnieuw ontdekken** in Home Assistant. De bedrijfsmodus verwarmen, koelen of stand-by geldt voor de hele basisunit.

De integratie controleert het WLAN-serienummer voordat ze bij een bekende verdeler een nieuw adres overneemt. Bij problemen kun je het adres aanpassen via **Configureren > Verbindingsinstellingen**.

De kaart en integratie volgen de taal van Home Assistant. Nederlands, Engels, Duits, Frans en Italiaans zijn beschikbaar. Meld problemen via [GitHub Issues](https://github.com/roelbroersma/viega-fonterra-smart-control/issues) en voeg je Home Assistant-versie en de relevante foutmelding toe.

## English quick start

Enable Modbus TCP on your Viega controller, [add the repository to HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=roelbroersma&repository=viega-fonterra-smart-control&category=integration), install and restart Home Assistant. Add **Viega Fonterra Smart** under **Settings > Devices & services** and select it in the dashboard card picker. With [Connected Upgrade](https://www.gigaweb.nl/fonterra-smart-control-upgrade/), select external measurement for the room in Fonterra, then link an existing temperature sensor under **Configure > Connect Upgrade**.

## Ontwikkeling

[Tests, bouwinstructies en release-informatie](RELEASE.md) · [Bronnen en licenties](THIRD_PARTY_NOTICES.md)
