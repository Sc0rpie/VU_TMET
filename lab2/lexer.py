import re
from enum import Enum, auto
from dataclasses import dataclass


class TokenKind(Enum):
    BLANK = auto()
    COMMENT = auto()
    ERROR = auto()
    FONT_DEFINITION = auto()
    DEFAULT_CHAR = auto()
    FONT_CHARSET = auto()
    EXCLUSION = auto()
    INPUT_TEXT_CHARSET = auto()


@dataclass
class Token:
    kind: TokenKind
    line: int
    raw: str


# --- regex patterns
WS_ONLY = re.compile(r"^[ \t]*$")
COMMENT = re.compile(r"^[ \t]*#(.*)$")
FONT_DEFINITION = re.compile(
    "^(dialog|dialoginput|serif|sansserif|monospaced|timesroman|helvetica|courier|zapfdingbats)\\.\\d+=(.+)$"
)
DEFAULT_CHAR = re.compile("^default\\.char=([0-9]+)$")
FONT_CHARSET = re.compile("^fontcharset\\.(dialog|dialoginput|serif|sansserif|monospaced)\\.\\d+=.+$")
EXCLUSION = re.compile("^exclusion\\.(dialog|dialoginput|serif|sansserif|monospaced)\\.\\d+=[0-9a-fA-F]+-[0-9a-fA-F]+$")
INPUT_TEXT_CHARSET = re.compile("^inputtextcharset=.+$")


def lex_line(raw: str, line_no: int) -> Token:
    line = raw.rstrip("\r\n")

    if WS_ONLY.match(line):
        return Token(TokenKind.BLANK, line_no, raw)

    if COMMENT.match(line):
        return Token(TokenKind.COMMENT, line_no, raw)

    if FONT_DEFINITION.match(line):
        return Token(TokenKind.FONT_DEFINITION, line_no, raw)

    if DEFAULT_CHAR.match(line):
        return Token(TokenKind.DEFAULT_CHAR, line_no, raw)

    if FONT_CHARSET.match(line):
        return Token(TokenKind.FONT_CHARSET, line_no, raw)

    if EXCLUSION.match(line):
        return Token(TokenKind.EXCLUSION, line_no, raw)

    if INPUT_TEXT_CHARSET.match(line):
        return Token(TokenKind.INPUT_TEXT_CHARSET, line_no, raw)

    return Token(TokenKind.ERROR, line_no, raw)


def lex_file(path: str):
    tokens = []
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            tokens.append(lex_line(line, i))
    return tokens


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python lexer.py font.properties")
        sys.exit(1)

    tokens = lex_file(sys.argv[1])
    for t in tokens:
        print(f"{t.line:>3}  {t.kind.name:<8}  {t.raw.strip()}")
