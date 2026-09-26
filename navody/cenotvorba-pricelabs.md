# Cenotvorba přes PriceLabs

PriceLabs každý den přepočítá ceny všech apartmánů podle poptávky, sezóny, akcí ve městě a cen konkurence.
Nové ceny pošle do Smoobu a Smoobu je rozešle na Airbnb i Booking.
Cena je cca 20 $ měsíčně za apartmán. Prvních 30 dní je zdarma.

## Postup
1. Založ si účet na **pricelabs.co**.
2. Zvol **Smoobu** jako svůj channel manager a propoj ho (PriceLabs tě provede přihlášením do Smoobu).
3. Ve Smoobu zapni pro apartmány **synchronizaci cen**, jinak se ceny od PriceLabs nepropíšou na platformy.
4. U každého apartmánu nastav:

| Nastavení | Co to je | Doporučený start |
|---|---|---|
| **Base price** | „normální“ cena za noc | PriceLabs ji navrhne. Porovnej s tím, za kolik pronajímáš teď. |
| **Min price** | pod tuto cenu nikdy nejde | Náklady na noc (úklid, energie, provize) + malá rezerva |
| **Max price** | strop | cca 3× base price |
| **Minimum stay** | minimální počet nocí | 2 noci, v posledních 7 dnech 1 noc |
| **Last-minute** | sleva na volné termíny těsně před datem | −10 až −20 % v posledních 7 dnech |
| **Orphan gaps** | 1–2 volné noci mezi rezervacemi | povolit kratší pobyt a dát slevu |
| **Far-out premium** | vyšší cena pro termíny daleko dopředu | +10 % na termíny za 3+ měsíce |

5. První 2 týdny nech PriceLabs jen **navrhovat**. Až budou návrhy dávat smysl, zapni **automatickou synchronizaci**.
6. Jednou týdně se podívej na obsazenost. Když máš byty moc brzy plné, jsi levný. Když máš prázdné termíny do 14 dní, jsi drahý.

## Proč ne vlastní algoritmus?
PriceLabs má data o obsazenosti a cenách tisíců bytů v Praze, která my nemáme. Vlastní ceník by „střílel naslepo“.
Agent se k cenám může přidat později, například týdenním přehledem obsazenosti a tržeb.
