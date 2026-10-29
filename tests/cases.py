"""Editing scenarios shared by the isfped regression tests and the SPFLite
comparison.

A case is (name, input lines, steps). A step is
    ("L", {line: command, ...})  type line commands, then one Enter
    ("P", "primary command")     type a primary command, then Enter
The file is saved afterwards and the saved lines are the result.
SPFLite runs a ("L", ...) step as one LINE primary command per line,
bottom line first so earlier commands don't renumber later ones.
"""

BASE = [
    "alpha one",
    "  beta two",
    "gamma three",
    "    delta four",
    "epsilon five",
    "zeta six",
    "eta seven",
    "theta eight",
    "iota nine",
    "kappa ten",
]

MIXED = ["Hello World", "MIXED Case line", "lower only", "UPPER ONLY"]

PARA = [
    "The quick brown fox",
    "jumps over",
    "the lazy dog and keeps running far away.",
    "",
    "Second paragraph here.",
]

SORTME = ["pear 3", "apple 10", "Banana 2", "cherry 1", "apple 2"]

COLS = ["abcabc", "xabcx", "abc abc", "cab abcd", "ab"]


def L(**kw):
    """L(_3="D") -> ("L", {3: "D"}); keyword names are _<line>."""
    return ("L", {int(k[1:]): v for k, v in kw.items()})


def P(cmd):
    return ("P", cmd)


CASES = [
    # --- Delete ----------------------------------------------------------
    ("D single", BASE, [L(_3="D")]),
    ("D count D3", BASE, [L(_3="D3")]),
    ("D count past end", BASE, [L(_9="D5")]),
    ("D count to last line", BASE, [L(_8="D3")]),
    ("X count past end", BASE, [L(_9="X5")]),
    ("UC count past end", BASE, [L(_9="UC5")]),
    ("C count past end", BASE, [L(_9="C5", _1="A")]),
    ("D first line", BASE, [L(_1="D")]),
    ("D last line", BASE, [L(_10="D")]),
    ("DD block", BASE, [L(_3="DD", _5="DD")]),
    ("D two lines one Enter", BASE, [L(_2="D", _5="D")]),
    ("DD block reversed order typed", BASE, [L(_2="DD"), L(_4="DD")]),
    # --- Insert (untouched inserted lines vanish) ------------------------
    ("I untouched dropped", BASE, [L(_3="I")]),
    ("I5 untouched dropped", BASE, [L(_3="I5")]),
    # --- Repeat ----------------------------------------------------------
    ("R single", BASE, [L(_2="R")]),
    ("R3", BASE, [L(_2="R3")]),
    ("RR block", BASE, [L(_2="RR", _3="RR")]),
    ("RR block count", BASE, [L(_2="RR2", _3="RR")]),
    ("R last line", BASE, [L(_10="R")]),
    # --- Copy / move -----------------------------------------------------
    ("C A", BASE, [L(_2="C", _5="A")]),
    ("C B", BASE, [L(_2="C", _5="B")]),
    ("C3 A", BASE, [L(_2="C3", _9="A")]),
    ("CC A", BASE, [L(_2="CC", _3="CC", _5="A")]),
    ("CC B first", BASE, [L(_4="CC", _5="CC", _1="B")]),
    ("CC then A later Enter", BASE, [L(_2="CC"), L(_3="CC"), L(_5="A")]),
    ("C A2 repeat dest", BASE, [L(_2="C", _5="A2")]),
    ("M A", BASE, [L(_2="M", _5="A")]),
    ("M B up", BASE, [L(_7="M", _2="B")]),
    ("M2 A", BASE, [L(_2="M2", _9="A")]),
    ("MM A", BASE, [L(_2="MM", _3="MM", _8="A")]),
    ("MM B top", BASE, [L(_7="MM", _8="MM", _1="B")]),
    ("C last line A", BASE, [L(_10="C", _9="A")]),
    ("C O overlay", ["ab  ef", "  cd  gh"], [L(_1="C", _2="O")]),
    ("CC OO overlay", ["x", "y ", "    1", "    2", "    3"],
     [L(_1="CC", _2="CC", _3="OO", _5="OO")]),
    # --- Case ------------------------------------------------------------
    ("UC", MIXED, [L(_1="UC")]),
    ("UC3", MIXED, [L(_1="UC3")]),
    ("UCC block", MIXED, [L(_1="UCC", _3="UCC")]),
    ("LC", MIXED, [L(_2="LC")]),
    ("LCC block", MIXED, [L(_1="LCC", _4="LCC")]),
    # --- Shifts ----------------------------------------------------------
    ("( column shift left", BASE, [L(_1="(")]),
    ("(4 column shift left", BASE, [L(_4="(4")]),
    (") column shift right", BASE, [L(_1=")")]),
    (")5", BASE, [L(_1=")5")]),
    ("(( block", BASE, [L(_2="((", _4="((")]),
    ("))3 block", BASE, [L(_2="))3", _4="))")]),
    ("< data shift left", BASE, [L(_4="<")]),
    ("<6 data shift beyond indent", BASE, [L(_4="<6")]),
    ("> data shift right", BASE, [L(_1=">")]),
    ("<< block", BASE, [L(_2="<<", _4="<<")]),
    ("( on unindented loses data", ["abcdef"], [L(_1="(3")]),
    ("< on unindented keeps data", ["abcdef"], [L(_1="<3")]),
    ("> on indented line", BASE, [L(_2=">")]),
    (">3 on one word", ["abcdef"], [L(_1=">3")]),
    (">3 widens first gap", ["ab cd  ef"], [L(_1=">3")]),
    ("<3 closes first gap", ["ab     cd ef"], [L(_1="<3")]),
    ("<3 first gap too small", ["ab  cd   ef"], [L(_1="<3")]),
    ("<6 indent then inner gap", ["   ab     cd"], [L(_1="<6")]),
    (">>3 block", BASE, [L(_1=">>3", _2=">>")]),
    # --- Exclude ---------------------------------------------------------
    ("X then D on block", BASE, [L(_3="X3"), L(_3="D")]),
    ("XX then DELETE ALL X", BASE, [L(_2="XX", _4="XX"), P("DELETE ALL X")]),
    ("XX then DELETE ALL NX", BASE, [L(_2="XX", _4="XX"), P("DELETE ALL NX")]),
    ("X ALL, FIND ALL, DELETE ALL X", BASE,
     [P("X ALL"), P("FIND ALL eta"), P("DELETE ALL X")]),
    ("X string ALL, DELETE ALL X", BASE, [P("X ALL 'ta'"), P("DELETE ALL X")]),
    ("X ALL, F on block shows first", BASE,
     [P("X ALL"), L(_1="F2"), P("DELETE ALL X")]),
    ("X ALL, L on block shows last", BASE,
     [P("X ALL"), L(_1="L3"), P("DELETE ALL X")]),
    ("C ALL NX", BASE, [L(_1="XX", _5="XX"), P("C ALL e E NX")]),
    ("C ALL X", BASE, [L(_1="XX", _5="XX"), P("C ALL e E X")]),
    ("XX then CC on block A", BASE,
     [L(_2="XX", _3="XX"), L(_2="C", _6="A")]),
    # --- Text flow -------------------------------------------------------
    ("TF20", PARA, [L(_1="TF20")]),
    ("TF30 second para", PARA, [L(_5="TF30")]),
    # --- Labels ----------------------------------------------------------
    ("labels DELETE range", BASE,
     [L(_3=".AA", _6=".BB"), P("DELETE .AA .BB")]),
    ("labels C ALL range", BASE,
     [L(_3=".AA", _6=".BB"), P("C ALL e E .AA .BB")]),
    ("labels SORT range", BASE,
     [L(_6=".AA", _9=".BB"), P("SORT .AA .BB")]),
    ("pseudo labels DELETE .3 .5", BASE, [P("DELETE .3 .5")]),
    ("pseudo labels SORT .3 .6", BASE, [P("SORT .3 .6")]),
    ("pseudo labels UC .2 .4", BASE, [P("UC .2 .4")]),
    ("pseudo labels C ALL .2 .4", BASE, [P("C ALL e E .2 .4")]),
    ("pseudo label past end", BASE, [P("UC .2 .15")]),
    ("label follows move", BASE,
     [L(_5=".AA"), L(_1="D"), P("DELETE .AA .AA")]),
    # --- CHANGE ----------------------------------------------------------
    ("C ALL", BASE, [P("C ALL e E")]),
    ("C first from top", BASE, [P("C e E")]),
    ("C at line 1 col 1", BASE, [P("C alpha ALPHA")]),
    ("C LAST", BASE, [P("C e E LAST")]),
    ("C then RCHANGE", BASE, [P("C e E"), P("RCHANGE"), P("RCHANGE")]),
    ("C ALL columns", COLS, [P("C ALL abc X 2 4")]),
    ("C ALL WORD", COLS, [P("C ALL abc Z WORD")]),
    ("C ALL PREFIX", COLS, [P("C ALL abc Z PREFIX")]),
    ("C ALL SUFFIX", COLS, [P("C ALL abc Z SUFFIX")]),
    ("C ALL caseless", MIXED, [P("C ALL o 0")]),
    ("C ALL C'' exact", MIXED, [P("C ALL C'O' 0")]),
    ("C ALL quoted space", BASE, [P("C ALL ' t' '_T'")]),
    ("C ALL to empty", BASE, [P("C ALL 'e' ''")]),
    ("C ALL hex string", BASE, [P("C ALL X'61' '@'")]),
    ("C ALL longer replacement", BASE, [P("C ALL a aaa")]),
    ("C not found", BASE, [P("C ALL zzz yyy")]),
    ("FIND then C NEXT", BASE, [P("F theta"), P("C e E")]),
    # --- DELETE / SORT ---------------------------------------------------
    ("DELETE without operands refused", BASE, [P("DELETE")]),
    ("DELETE ALL X with nothing excluded", BASE, [P("DELETE ALL X")]),
    ("SORT", SORTME, [P("SORT")]),
    ("SORT D", SORTME, [P("SORT D")]),
    ("SORT columns", SORTME, [P("SORT 2 3")]),
    ("SORT two fields", SORTME, [P("SORT A 1 5 D 7 8")]),
    # --- UNDO / RESET ----------------------------------------------------
    ("UNDO line command", BASE, [L(_2="D"), P("UNDO")]),
    ("UNDO twice", BASE, [L(_2="D"), L(_2="D"), P("UNDO"), P("UNDO")]),
    ("RESET discards pending", BASE, [L(_2="CC"), P("RESET"), L(_5="D")]),
    # --- whole buffer ----------------------------------------------------
    ("primary UC", MIXED, [P("UC")]),
    ("primary LC", MIXED, [P("LC")]),
    ("primary UC ALL", MIXED, [P("UC ALL")]),
    ("primary LC .ZF .ZL", MIXED, [P("LC .ZF .ZL")]),
    ("primary UC labels", MIXED, [L(_2=".AA"), L(_3=".BB"), P("UC .AA .BB")]),
    ("primary UC one label", MIXED, [P("UC .2")]),
]
