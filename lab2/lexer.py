import re
from enum import Enum, auto
from dataclasses import dataclass

class TokenKind(Enum):
    BLANK = auto()
    COMMENT = auto()
    ERROR = auto()

@dataclass
class Token:
    kind: TokenKind
    line: int
    raw: str

# --- regex patterns
WS_ONLY   = re.compile(r'^[ \t]*$')
COMMENT   = re.compile(r'^[ \t]*#(.*)$')

def lex_line(raw: str, line_no: int) -> Token:
    # strip CR if CRLF
    line = raw.rstrip("\r\n")

    # BLANK
    if WS_ONLY.match(line):
        return Token(TokenKind.BLANK, line_no, raw)

    # COMMENT
    if COMMENT.match(line):
        return Token(TokenKind.COMMENT, line_no, raw)

    # ERROR
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