"""Vocabulary of the rule-based interpreter (spec §6.1).

Phrases are matched case-insensitively; symbols keep their case (spec §5.3).
"""

from typing import Final

NUMBER_WORDS: Final = {
    word: value
    for value, word in enumerate(
        (
            *("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"),
            *("ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen"),
            *("seventeen", "eighteen", "nineteen", "twenty"),
        )
    )
}
TIMES_WORDS: Final = {"once": 1, "twice": 2, "thrice": 3}
ORDINAL_WORDS: Final = {
    word: value
    for value, word in enumerate(
        (
            *("first", "second", "third", "fourth", "fifth"),
            *("sixth", "seventh", "eighth", "ninth", "tenth"),
        ),
        start=1,
    )
}

# Qualifier → (operator, adjustment to n): "more than 2" means at least 3.
QUALIFIERS: Final = {
    "exactly": ("eq", 0),
    "precisely": ("eq", 0),
    "at least": ("ge", 0),
    "no fewer than": ("ge", 0),
    "no less than": ("ge", 0),
    "a minimum of": ("ge", 0),
    "more than": ("ge", 1),
    "at most": ("le", 0),
    "no more than": ("le", 0),
    "not more than": ("le", 0),
    "up to": ("le", 0),
    "a maximum of": ("le", 0),
    "fewer than": ("le", -1),
    "less than": ("le", -1),
}

NUMBER: Final = r"(?:\d+|" + "|".join(NUMBER_WORDS) + r")"
QUALIFIER: Final = "|".join(sorted(QUALIFIERS, key=len, reverse=True))
ORDINAL: Final = r"(?:" + "|".join(ORDINAL_WORDS) + r"|\d+(?:st|nd|rd|th))"
SYMBOL_NOUN: Final = r"(?:symbol|letter|character|bit|digit)"
HAVE: Final = r"(?:contains?|containing|includes?|including|has|have|having|with)"

# Words that only introduce the description, stripped from the front of a clause.
LEADING_FILLER: Final = (
    r"^(?:(?:all|the|set|of|language|strings?|words?|sequences?|binary|bit|bitstrings?|that|"
    r"which|whose|"
    r"where|such|in|are|is|those|any|both|either|also)\s+)+"
)
# What may come before the description, stripped from the front of the sentence one
# piece at a time and in any order: "Please enter all binary strings …", "Can you
# construct an NFA for the language of all strings …". Articles go only with a machine
# noun and all/every/any/each only before strings or words, so "a or b followed by c"
# and "every a is followed by b" keep their first word.
_COMMANDS: Final = (
    r"enter|type|give(?: me)?|write(?: down)?|make|build|create|generate|find|show(?: me)?|"
    r"list|construct|design|draw|input"
)
_MACHINE: Final = (
    r"(?:(?:ε|epsilon|e)-?)?nfa|dfa|(?:finite )?automaton|(?:finite[- ]state )?machine"
)
_RECOGNISES: Final = r"accepting|accepts?|recogni[sz](?:es|ing|e)"
LEAD_IN: Final = (
    r"^(?:please|kindly|(?:can|could|would) you|i (?:want|need|would like)(?: to)?"
    r"|i'd like(?: to)?"
    rf"|{_COMMANDS}"
    rf"|(?:an? |the )?(?:{_MACHINE})(?: (?:for|(?:that |which )?(?:{_RECOGNISES})))?"
    rf"|(?:that |which )?(?:{_RECOGNISES})"
    r"|(?:the )?(?:language|set) of"
    r"|(?:an? |the )?(?:string|word|input)(?: w)? is (?:accepted|in the language) "
    r"(?:iff|if and only if|exactly when|precisely when|when|if)(?: it)?"
    r"|(?:all|every|any|each)(?= (?:the )?(?:binary )?(?:strings?|words?|sequences?)\b)"
    r")[\s,:]+"
)
NEGATION: Final = (
    r"^(?:that |which )?(?:do not|does not|don't|doesn't|dont|doesnt|not|never|cannot|can't"
    r"|except(?: for)?(?: those| the ones| strings| words)?(?: that| which)?)\s+"
)
# Splits clauses; "but", "plus", "while" and a relative "that"/"which" join like "and".
CONNECTIVE: Final = r"\s*,?\s+\b(and|but|or|as well as|plus|while|that|which)\b\s+"

# Words the rules know, for correcting a misspelled one to the closest (C18). Only words
# of five or more letters are ever corrected, so short words need not be listed.
VOCABULARY: Final = frozenset(
    {
        *NUMBER_WORDS,
        *ORDINAL_WORDS,
        *[
            "start",
            "starts",
            "started",
            "starting",
            "begin",
            "begins",
            "beginning",
            "began",
            "begun",
            "end",
            "ends",
            "ended",
            "ending",
            "finish",
            "finishes",
            "finished",
            "finishing",
            "contain",
            "contains",
            "contained",
            "containing",
            "include",
            "includes",
            "included",
            "including",
            "having",
            "without",
            "avoid",
            "avoids",
            "avoiding",
            "appear",
            "appears",
            "occur",
            "occurs",
            "somewhere",
            "never",
            "prefix",
            "suffix",
            "substring",
            "subword",
            "factor",
            "infix",
            "pattern",
            "string",
            "strings",
            "words",
            "symbol",
            "symbols",
            "letter",
            "letters",
            "character",
            "characters",
            "digit",
            "digits",
            "binary",
            "alphabet",
            "language",
            "exactly",
            "precisely",
            "least",
            "most",
            "more",
            "fewer",
            "times",
            "twice",
            "thrice",
            "number",
            "count",
            "amount",
            "length",
            "divisible",
            "multiple",
            "modulo",
            "congruent",
            "consecutive",
            "occurrence",
            "occurrences",
            "instance",
            "instances",
            "copies",
            "copy",
            "repetitions",
            "repeats",
            "appearances",
            "followed",
            "preceded",
            "immediately",
            "directly",
            "every",
            "other",
            "first",
            "second",
            "third",
            "fourth",
            "fifth",
            "sixth",
            "seventh",
            "eighth",
            "ninth",
            "tenth",
            "final",
            "equal",
            "equals",
            "whose",
            "where",
            "which",
            "their",
            "there",
            "these",
            "those",
            "other",
            "either",
            "neither",
            "plus",
            "while",
            "regular",
            "expression",
            "regex",
            "matching",
            "matches",
            "matched",
            "described",
            "generated",
            "given",
            "form",
            "match",
            "accept",
            "accepts",
            "accepting",
            "recognise",
            "recognises",
            "recognize",
            "recognizes",
            "please",
            "enter",
            "construct",
            "design",
            "build",
            "create",
            "generate",
            "write",
            "draw",
            "input",
            "show",
            "sequence",
            "sequences",
            "maximum",
            "minimum",
        ],
    }
)

# Single symbols whose conventional partner completes an inferred alphabet (C5).
PARTNERS: Final = {"0": "1", "1": "0", "a": "b", "b": "a"}
# Wording that hints at more symbols than the description mentions (spec §6.2); it is
# taken out of the sentence once noted.
ALPHABET_HINTS: Final = r"\b(?:over (?:the )?letters|any characters?|any symbols?|letters)\b"

# Assumption ids and texts as in benchmark_v1, with whether the UI may toggle them.
ASSUMPTIONS: Final = {
    "zero_is_even": ("Zero occurrences counts as even.", False),
    "alphabet_inferred": ("The alphabet was inferred from the description.", True),
    "avoids_consecutive": ("'No two consecutive x' is read as: does not contain xx.", True),
    "length_includes_empty": ("Length 0 (the empty string ε) is included.", True),
    "same_symbol_nonempty": ("Only non-empty strings are considered; ε is excluded.", True),
    "llm_interpreted": (
        "This reading was proposed by a language model; check it before building.",
        False,
    ),
    "no_overlap_possible": (
        "Occurrences of the pattern cannot overlap, so no choice is needed.",
        False,
    ),
}

# C11: offered when a description cannot be read at all.
EXAMPLE_PROMPTS: Final = (
    "binary strings ending in 01",
    "strings over {a,b} with an even number of a's",
    "strings over {a,b} that contain aba but do not end with b",
)
# The closest of these to an unreadable description is suggested first (C11).
EXAMPLE_CATALOG: Final = (
    *EXAMPLE_PROMPTS,
    "binary strings starting with 1",
    "strings over {a,b} containing the substring abba",
    "binary strings that contain 101 and end with 00",
    "binary strings of odd length",
    "binary strings whose length is divisible by 3",
    "binary strings with no two consecutive 1s",
    "strings over {a,b} with at least three a's",
)
