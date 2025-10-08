import re
from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional
import re
from dataclasses import dataclass
from typing import List, Optional
import sys


class TokenKind(Enum):
    # Structural tokens
    BLANK = auto()
    COMMENT = auto()
    ERROR = auto()

    # Operators and delimiters
    DOT = auto()
    EQUALS = auto()
    MINUS = auto()
    COMMA = auto()

    # Keywords and identifiers
    FONT_FAMILY = auto()
    DEFAULT = auto()
    CHAR = auto()
    FONTCHARSET = auto()
    EXCLUSION = auto()
    INPUTTEXTCHARSET = auto()

    # Values
    NUMBER = auto()
    HEX_NUMBER = auto()
    STRING = auto()


@dataclass
class Token:
    kind: TokenKind
    line: int
    column: int
    value: str
    raw: str


class Lexer:
    def __init__(self, text: str, line_no: int = 1):
        self.text = text
        self.pos = 0
        self.line_no = line_no
        self.column = 1
        self.tokens: List[Token] = []

    def current_char(self) -> Optional[str]:
        if self.pos < len(self.text):
            return self.text[self.pos]
        return None

    def advance(self) -> str:
        ch = self.current_char()
        self.pos += 1
        self.column += 1
        return ch

    def skip_whitespace(self):
        while self.current_char() and self.current_char() in " \t":
            self.advance()

    def read_while(self, predicate) -> str:
        start_pos = self.pos
        while self.current_char() and predicate(self.current_char()):
            self.advance()
        return self.text[start_pos : self.pos]

    def tokenize_line(self) -> List[Token]:
        self.tokens = []

        # Skip whitespace at start
        self.skip_whitespace()

        # Check for blank line
        if not self.current_char() or self.current_char() in "\r\n":
            self.tokens.append(Token(TokenKind.BLANK, self.line_no, 1, "", ""))
            return self.tokens

        # Check for comment
        if self.current_char() == "#":
            start_col = self.column
            self.advance()
            comment_text = self.read_while(lambda c: c not in "\r\n")
            self.tokens.append(
                Token(TokenKind.COMMENT, self.line_no, start_col, comment_text.strip(), "#" + comment_text)
            )
            return self.tokens

        # Parse the line structure
        while self.pos < len(self.text) and self.current_char() not in "\r\n":
            self.skip_whitespace()

            if not self.current_char() or self.current_char() in "\r\n":
                break

            ch = self.current_char()

            if ch == ".":
                start_col = self.column
                self.advance()
                self.tokens.append(Token(TokenKind.DOT, self.line_no, start_col, ".", "."))

            elif ch == "=":
                start_col = self.column
                self.advance()
                self.tokens.append(Token(TokenKind.EQUALS, self.line_no, start_col, "=", "="))

                # Everything after = is the value (could be comma-separated)
                self.skip_whitespace()
                if self.current_char() and self.current_char() not in "\r\n":
                    start_col = self.column
                    value_text = self.read_while(lambda c: c not in "\r\n")
                    value_text = value_text.strip()

                    # Split by commas but keep as one STRING token with the full value
                    self.tokens.append(Token(TokenKind.STRING, self.line_no, start_col, value_text, value_text))

            elif ch == "-":
                start_col = self.column
                self.advance()
                self.tokens.append(Token(TokenKind.MINUS, self.line_no, start_col, "-", "-"))

            elif ch.isdigit():
                start_col = self.column
                value = self.read_while(lambda c: c in "0123456789abcdefABCDEF")

                # Determine if hex or decimal
                if any(c in "abcdefABCDEF" for c in value):
                    self.tokens.append(Token(TokenKind.HEX_NUMBER, self.line_no, start_col, value, value))
                else:
                    self.tokens.append(Token(TokenKind.NUMBER, self.line_no, start_col, value, value))

            elif ch.isalpha() or ch == "_":
                start_col = self.column
                value = self.read_while(lambda c: c.isalnum() or c in "_.-")

                # Identify keywords
                kind_map = {
                    "dialog": TokenKind.FONT_FAMILY,
                    "dialoginput": TokenKind.FONT_FAMILY,
                    "serif": TokenKind.FONT_FAMILY,
                    "sansserif": TokenKind.FONT_FAMILY,
                    "monospaced": TokenKind.FONT_FAMILY,
                    "timesroman": TokenKind.FONT_FAMILY,
                    "helvetica": TokenKind.FONT_FAMILY,
                    "courier": TokenKind.FONT_FAMILY,
                    "zapfdingbats": TokenKind.FONT_FAMILY,
                    "default": TokenKind.DEFAULT,
                    "char": TokenKind.CHAR,
                    "fontcharset": TokenKind.FONTCHARSET,
                    "exclusion": TokenKind.EXCLUSION,
                    "inputtextcharset": TokenKind.INPUTTEXTCHARSET,
                }

                kind = kind_map.get(value.lower(), TokenKind.STRING)
                self.tokens.append(Token(kind, self.line_no, start_col, value, value))

            else:
                start_col = self.column
                self.advance()
                self.tokens.append(Token(TokenKind.ERROR, self.line_no, start_col, ch, ch))

        return self.tokens


# ============== PARSER PART ==============


@dataclass
class Statement:
    line: int
    kind: str
    raw: str


@dataclass
class FontDefinition(Statement):
    font_family: str
    index: int
    font_name: str
    charset: str
    flags: List[str]


@dataclass
class DefaultChar(Statement):
    value: int


@dataclass
class FontCharset(Statement):
    font_family: str
    index: int
    class_path: str


@dataclass
class Exclusion(Statement):
    font_family: str
    index: int
    range_start: str
    range_end: str


@dataclass
class InputTextCharset(Statement):
    charset: str


@dataclass
class Comment(Statement):
    text: str


@dataclass
class Error(Statement):
    pass


class Parser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.statements = []

        # Define regex patterns for each statement type
        self.patterns = {
            "font_def": re.compile(
                r"^(dialog|dialoginput|serif|sansserif|monospaced|timesroman|helvetica|courier|zapfdingbats)\.(\d+)=(.+)$"
            ),
            "default_char": re.compile(r"^default\.char=(\d+)$"),
            "font_charset": re.compile(r"^fontcharset\.(dialog|dialoginput|serif|sansserif|monospaced)\.(\d+)=(.+)$"),
            "exclusion": re.compile(
                r"^exclusion\.(dialog|dialoginput|serif|sansserif|monospaced)\.(\d+)=([0-9a-fA-F]+)-([0-9a-fA-F]+)$"
            ),
            "input_charset": re.compile(r"^inputtextcharset=(.+)$"),
            "comment": re.compile(r"^#.*$"),
            "blank": re.compile(r"^[ \t]*$"),
        }

    def parse(self):
        with open(self.filepath, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                original_line = line.rstrip("\r\n")
                line = line.strip()

                # Skip truly blank lines
                if not line:
                    continue

                stmt = self.parse_line(line, original_line, line_no)
                if stmt:
                    self.statements.append(stmt)

        return self.statements

    def parse_line(self, line: str, original: str, line_no: int) -> Optional[Statement]:
        # Check for comment
        if self.patterns["comment"].match(line):
            comment_text = line[1:].strip() if len(line) > 1 else ""
            return Comment(line_no, "Comment", original, comment_text)

        # Check for blank line
        if self.patterns["blank"].match(line):
            return None

        # Try font definition pattern
        match = self.patterns["font_def"].match(line)
        if match:
            family = match.group(1)
            index = int(match.group(2))
            value_str = match.group(3)

            # Split the comma-separated values
            parts = [p.strip() for p in value_str.split(",")]
            font_name = parts[0] if parts else ""
            charset = parts[1] if len(parts) > 1 else ""
            flags = parts[2:] if len(parts) > 2 else []

            return FontDefinition(line_no, "FontDefinition", original, family, index, font_name, charset, flags)

        # Try default char pattern
        match = self.patterns["default_char"].match(line)
        if match:
            value = int(match.group(1))
            return DefaultChar(line_no, "DefaultChar", original, value)

        # Try font charset pattern
        match = self.patterns["font_charset"].match(line)
        if match:
            family = match.group(1)
            index = int(match.group(2))
            class_path = match.group(3)
            return FontCharset(line_no, "FontCharset", original, family, index, class_path)

        # Try exclusion pattern
        match = self.patterns["exclusion"].match(line)
        if match:
            family = match.group(1)
            index = int(match.group(2))
            range_start = match.group(3)
            range_end = match.group(4)
            return Exclusion(line_no, "Exclusion", original, family, index, range_start, range_end)

        # Try input charset pattern
        match = self.patterns["input_charset"].match(line)
        if match:
            charset = match.group(1)
            return InputTextCharset(line_no, "InputTextCharset", original, charset)

        # If nothing matches, it's an error
        return Error(line_no, "KLAIDA", original)


def print_output(statements: List[Statement]):
    for stmt in statements:
        if isinstance(stmt, Error):
            print(f"Eilutė {stmt.line}: KLAIDA")
            print(f"    {stmt.raw}")
        elif isinstance(stmt, Comment):
            # Skip printing comments in main output
            continue
        else:
            print(f"Eilutė {stmt.line}: {stmt.kind}")

            if isinstance(stmt, FontDefinition):
                print(f"    Šeima: {stmt.font_family}")
                print(f"    Indeksas: {stmt.index}")
                print(f"    Šriftas: {stmt.font_name}")
                if stmt.charset:
                    print(f"    Simbolių rinkinys: {stmt.charset}")
                if stmt.flags:
                    print(f"    Vėliavos: {', '.join(stmt.flags)}")

            elif isinstance(stmt, DefaultChar):
                print(f"    Reikšmės: {stmt.value}")

            elif isinstance(stmt, FontCharset):
                print(f"    Šeimos: {stmt.font_family}")
                print(f"    Indeksas: {stmt.index}")
                print(f"    Klasė: {stmt.class_path}")

            elif isinstance(stmt, Exclusion):
                print(f"    Šeima: {stmt.font_family}")
                print(f"    Indeksas: {stmt.index}")
                print(f"    Diapazonas: {stmt.range_start}-{stmt.range_end}")

            elif isinstance(stmt, InputTextCharset):
                print(f"    Simbolių rinkinys: {stmt.charset}")

        print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Naudojimas: python parser.py font.properties")
        sys.exit(1)

    parser = Parser(sys.argv[1])
    statements = parser.parse()
    print_output(statements)

