# Bronnen en licenties

Deze integratie bouwt voort op [Viega Fonterra Smart Control van mikefogel](https://github.com/mikefogel/homeassistant-viega-fonterra-modbus), versie 1.3.5, commit `820c51bc02aaa6f471d1d8853db52c55d1099829`, onder de MIT-licentie. De bestaande Modbusclient, klimaatbediening, kamerontdekking en overige platformen zijn opgenomen in deze ene integratie.

De oorspronkelijke copyright- en MIT-vermelding blijft behouden in `LICENSE` en in de integratiemap. De eigen Connect-aanvullingen vallen eveneens onder MIT. De wiretests gebruiken de daadwerkelijk meegeleverde Modbusclient.

De verwijzingen naar `spec.md` in overgenomen code lopen naar de [specificatie van de oorspronkelijke integratie](https://github.com/mikefogel/homeassistant-viega-fonterra-modbus/blob/820c51bc02aaa6f471d1d8853db52c55d1099829/spec.md).

De registeradressen volgen de oorspronkelijke Viega Fonterra Smart Control 2.0-handleiding en het Connect Upgrade-addendum 1.1. De PDF's worden niet heruitgegeven. Viega en Fonterra zijn merken van hun rechthebbenden.

Het geel-zwarte Viega-beeldmerk in de Home Assistant-iconen is afkomstig van de [Viega-website](https://www.viega.nl/etc.clientlibs/viega-frontend/clientlibs/main/resources/icons/logo_w_border.svg). Alleen het transparante buitenvlak en de uitvoergrootte zijn aangepast voor vierkante iconen; het beeldmerk is niet nagetekend. Het beeldmerk blijft eigendom van Viega en valt niet onder de MIT-licentie van de integratie.
