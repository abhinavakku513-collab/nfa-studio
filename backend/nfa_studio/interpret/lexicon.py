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
    r"^(?:(?:all|the|set|of|language|strings?|words?|sequences?|binary|that|which|whose|"
    r"where|such|in|are|is|those|any|both|either)\s+)+"
)
# An exercise-style request around the description: "Construct an NFA (over …) accepting".
PREAMBLE: Final = (
    r"^(?:please\s+)?(?:(?:construct|design|build|create|draw|give|make|find|write)\s+"
    r"(?:me\s+)?(?:an?\s+|the\s+)?(?:(?:ε|epsilon|e)-?)?(?:nfa|dfa|automaton|finite automaton|"
    r"(?:finite[- ]state )?machine)\s+(?:that\s+|which\s+)?)?"
    r"(?:accepting|accepts?|recogni[sz](?:ing|es?))\s+(?:(?:every|each)\s+)?"
)
NEGATION: Final = r"^(?:that |which )?(?:do not|does not|don't|doesn't|not|never|cannot|can't)\s+"
# Splits clauses; "but", "plus", "while" and a relative "that"/"which" join like "and".
CONNECTIVE: Final = r"\s*,?\s+\b(and|but|or|as well as|plus|while|that|which)\b\s+"

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
