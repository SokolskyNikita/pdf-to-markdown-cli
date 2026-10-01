"""What the scanned-book benchmark contains and checks.

Each sample is ``samples/<name>.pdf`` with ``reference/<name>_p<N>.txt`` for
every PDF page N. Adding a page or a probe only needs a change here (plus the
new reference file); ``score.py`` reads everything else from the references.
"""

from __future__ import annotations

SAMPLES = {"vieira_cartas_pt": 8, "multatuli_brieven_nl": 5, "sevigne_lettres_fr": 3}
SPREADS = {"vieira_cartas_pt"}  # each PDF page shows two facing book pages

# (sample, page, text that must appear verbatim on that page). Each was checked
# against the page image; most are spellings that an OCR model or LLM "fixed".
SPELLING_PROBES = [
    ("vieira_cartas_pt", 0, "Lorena e Brandeburg"),
    ("vieira_cartas_pt", 0, "da pretenção dos bombardeiros"),
    ("vieira_cartas_pt", 0, "de um arcabuzaço"),
    ("vieira_cartas_pt", 0, "A Raínha de Suécia"),
    ("vieira_cartas_pt", 0, "todas as prègações"),
    ("vieira_cartas_pt", 0, "comerciante em Lisbon"),
    ("vieira_cartas_pt", 1, "a propínqua morte"),
    ("vieira_cartas_pt", 1, "nossa restituïção"),
    ("vieira_cartas_pt", 2, "nêstes últimos dias"),
    ("vieira_cartas_pt", 2, "Arquivo da Tôrre do Tombo"),
    ("vieira_cartas_pt", 2, "Ele se embarcom"),
    ("vieira_cartas_pt", 3, "se distribuirem ao"),
    ("vieira_cartas_pt", 3, "é ùnicamente o que"),
    ("vieira_cartas_pt", 4, "real benegnidade"),
    ("vieira_cartas_pt", 4, "e contìnuamente pede"),
    ("vieira_cartas_pt", 4, "fervorosos sacrificios"),
    ("vieira_cartas_pt", 4, "pôsto que tibios"),
    ("vieira_cartas_pt", 5, "Conde de Castslo Melhor"),
    ("vieira_cartas_pt", 5, "pelo zodiaco das"),
    ("vieira_cartas_pt", 6, "tornaram a freqüentar"),
    ("vieira_cartas_pt", 6, "e prémio da justiça"),
    ("vieira_cartas_pt", 7, "que me me ocupe"),
    ("vieira_cartas_pt", 7, "supôsto que são"),
    ("vieira_cartas_pt", 7, "quiseramos senão"),
    ("vieira_cartas_pt", 7, "Comuniquemo nos em Deus"),
    ("multatuli_brieven_nl", 0, "mis geloopen"),
    ("multatuli_brieven_nl", 0, "naar kopyprys"),
    ("multatuli_brieven_nl", 1, "la tonnerre en bouteilles"),
    ("multatuli_brieven_nl", 1, "en triomfant directement"),
    ("multatuli_brieven_nl", 1, "Je crois plûtot"),
    ("multatuli_brieven_nl", 2, "Périsse plûtot"),
    ("multatuli_brieven_nl", 2, "que bientot une balle"),
    ("multatuli_brieven_nl", 2, "du dégoutant mépris"),
    ("multatuli_brieven_nl", 2, "na valait plus rien"),
    ("multatuli_brieven_nl", 3, "noch eigenlyk voor iemand"),
    ("multatuli_brieven_nl", 4, "verloren tweeen gedood"),
    ("multatuli_brieven_nl", 4, "gewonnen, òf 4"),
    ("sevigne_lettres_fr", 0, "de la maréchale, étaient au nombre"),
    ("sevigne_lettres_fr", 0, "avait probablement écrit"),
    ("sevigne_lettres_fr", 1, "ni ouï parler"),
    ("sevigne_lettres_fr", 2, "s'il arrivoit le moindre"),
    ("sevigne_lettres_fr", 2, "petits enfants dont"),
]
