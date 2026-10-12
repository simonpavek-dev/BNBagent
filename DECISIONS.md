# DECISIONS

Rozhodnutí, která může udělat jen hostitel. Každé s možnostmi; po rozhodnutí doplnit výsledek a datum.

## D1 – Citlivá data ve veřejném repozitáři (otevřené, 12. 10. 2026)
Repo `simonpavek-dev/BNBagent` je veřejné (při založení bylo soukromé). V repu je:
- v současném `znalostni-baze/obecne.yaml`: WhatsApp čísla Simona a Michaela (v podpisu a v `nouzove_kontakty`),
- v historii commitů (`65c9a7a` → smazáno v `6feb0d3`): jméno skutečné hostky v příkladu ve staré specifikaci API.
Kódy, hesla ani klíče v historii nejsou (prověřeno grepem celé historie).

Možnosti:
- **A) Repo vrátit na soukromé** (GitHub → Settings → Danger zone → Change visibility). Nejrychlejší, nic se nemaže.
- **B) Nechat veřejné a vyčistit:** čísla přesunout z `obecne.yaml` mimo git (např. `.env` / soubor ignorovaný gitem),
  historii přepsat (`git filter-repo`) a force-push. Pozor: přepsání historie je nevratné a kopie (forky, cache)
  už mohou existovat – čísla by se tím z internetu jistě nesmazala.
- **C) Nechat veřejné, jen přesunout čísla mimo git** pro budoucnost; historii nechat.

Výsledek: _čeká na rozhodnutí_

## D2 – Výchozí stav existujících funkcí vs. pravidlo „nová funkce = přepínač, výchozí vypnuto“ (otevřené)
Napojení na aplikaci úklidů, nabídka dřívějšího check-inu a hodinová kontrola kalendáře běží bez vlastního přepínače.
Možnosti: A) doplnit přepínače, výchozí vypnuto, a na serveru je zapnout v `.env` (chování se nezmění);
B) nechat jak je a pravidlo platí jen pro nové funkce.

Výsledek: _čeká na rozhodnutí_
