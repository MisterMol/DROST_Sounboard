# Securitybeleid

Deze applicatie gebruikt lokaal HTTP op `127.0.0.1` en bestuurt audioapparaten. Houd privé-opnames, lokale databasebestanden, screenshots met persoonsgegevens en logbestanden uit publieke issues.

## Kwetsbaarheden melden

Gebruik bij voorkeur **GitHub Security Advisories** in de repository als private melding wanneer de eigenaar deze functie heeft ingeschakeld. Maak geen openbaar issue met werkende exploitcode, persoonlijke data of tokens. De eigenaar van de repository kan daarna afstemmen over herstel en publicatie.

## Ontwerpkeuzes

- Geen internetserver, alleen loopback.
- Schrijfverzoeken vereisen een per-start beveiligingstoken.
- Geen toetsenbordhook: Windows registreert alleen door de gebruiker gekozen hotkeys.
- Geen administratorrechten nodig voor DrostSoundboard. VB-CABLE is een aparte driverinstallatie onder verantwoordelijkheid van de maker VB-Audio.
- Geen automatische update of stille driverinstallatie.

De repository bevat ontwikkelsoftware, niet een security-geaudite release. Installeer geen onbekende builds die zich voordoen als DrostSoundboard.
