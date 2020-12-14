
import cStringIO

TOKEN_NUMBER = "TOKEN_NUMBER"
TOKEN_IDENTIFIER = "TOKEN_IDENTIFIER"
TOKEN_STRING = "TOKEN_STRING"
TOKEN_EQUALS = "TOKEN_EQUALS"
TOKEN_COMMENT = "TOKEN_COMMENT"
TOKEN_COMA = "TOKEN_COMA"
TOKEN_SEMICOLON = "TOKEN_SEMICOLON"
TOKEN_OPEN_DICT = "TOKEN_OPEN_DICT"
TOKEN_OPEN_LIST = "TOKEN_OPEN_LIST"
TOKEN_CLOSE_DICT = "TOKEN_CLOSE_DICT"
TOKEN_CLOSE_LIST = "TOKEN_CLOSE_LIST"
TOKEN_ERROR = "TOKEN_ERROR"
TOKEN_END = "TOKEN_END"


def is_delimiter(ch):
    return ch in ",/;(){}='\"" or ch.isspace()


class Parser(object):
    """
    This class enables the parsing of an plist stream (in the old format) and returns
    a dictionary or list object that is at the root of the plist stream.
    To use the scanner simply do: ::

        obj = Parser().parse(<string_or_stream>)
    """
    def parseFile(self, path, untokenize=False):
        with open(path, 'rb') as f:
            return self.parse(f, untokenize=untokenize)

    def parse(self, string_or_stream, untokenize=False):
        """
        Parses the input stream and returns a dictionary or list at the root of the stream.

        >>> Parser().parse("3")
        3

        >>> Parser().parse("'abc'")
        'abc'

        >>> Parser().parse("()")
        []

        >>> Parser().parse("(1)")
        [1]

        >>> Parser().parse("(1;)")
        [1]

        >>> Parser().parse("(1; 2; 3)")
        [1, 2, 3]

        >>> Parser().parse("(1; (a; b; c;))")
        [1, [a, b, c]]

        >>> Parser().parse("{}")
        {}

        >>> Parser().parse("{'a' = 1;}")
        {'a': 1}

        >>> Parser().parse("{ident = (1; 2)}")
        {ident: [1, 2]}

        >>> Parser().parse("{ident1 = 1; ident2 = 2}")
        {ident2: 2, ident1: 1}

        >>> Parser().parse("{ident = ()}")
        {ident: []}

        >>> Parser().parse("{ident = hello/world}")
        {ident: hello/world}
        """
        self.scanner = Scanner(string_or_stream)
        self.lookahead = None
        self.tokenizer = self.scanner.tokenize()
        return self.parse_value(untokenize=untokenize)

    def next_token(self, peek=False):
        out = self.lookahead
        if out:
            if not peek:
                self.lookahead = None
        else:
            out = self.tokenizer.next()
            if peek:
                self.lookahead = out
        # if not peek: print out
        return out

    def parse_value(self, untokenize=False):
        token = self.next_token()
        if token.toktype in (TOKEN_NUMBER, TOKEN_STRING, TOKEN_IDENTIFIER):
            if untokenize:
                return token.value
            return token
        elif token.toktype == TOKEN_OPEN_LIST:
            return self.parse_list(untokenize=untokenize)
        elif token.toktype == TOKEN_OPEN_DICT:
            return self.parse_dict(untokenize=untokenize)
        else:
            self.parse_exception("Invalid token found: %s", token)

    def parse_list(self, untokenize=False):
        out = []
        token = self.next_token(peek=True)
        while token.toktype != TOKEN_END:
            if token.toktype == TOKEN_CLOSE_LIST:
                if self.lookahead:      # consume the token if it is a lookahead one
                    self.next_token()
                break

            out.append(self.parse_value(untokenize=untokenize))

            token = self.next_token()
            if token.toktype not in (TOKEN_CLOSE_LIST, TOKEN_COMA, TOKEN_SEMICOLON):
                self.parse_exception("Expected ';', ',' or ')', Found: %s", token)
            elif token.toktype in (TOKEN_COMA, TOKEN_SEMICOLON):
                token = self.next_token(peek=True)
        return out

    def parse_dict(self, untokenize=False):
        out = PlistDict()
        token = self.next_token()
        while token.toktype != TOKEN_END:
            if token.toktype == TOKEN_CLOSE_DICT:
                break
            elif token.toktype not in (TOKEN_NUMBER, TOKEN_STRING, TOKEN_IDENTIFIER):
                self.parse_exception("Expected string or identifier, Found: %s", token)
            else:
                key = token.value
                token = self.next_token()
                if token.toktype != TOKEN_EQUALS:
                    self.parse_exception("Expected '=', Found: %s", token)

                out[key] = self.parse_value(untokenize=untokenize)

                token = self.next_token()
                if token.toktype not in (TOKEN_CLOSE_DICT, TOKEN_COMA, TOKEN_SEMICOLON):
                    self.parse_exception("Expected ',', ';', or '}', Found: %s", token)
                elif token.toktype in (TOKEN_COMA, TOKEN_SEMICOLON):
                    token = self.next_token()
        return out

    def parse_exception(self, fmt, *args):
        raise ParseException(self.scanner.line, self.scanner.column, fmt, *args)


class ParseException(Exception):
    def __init__(self, line, column, fmt, *args):
        super(ParseException, self).__init__(("Line: %d, Column: %d, %s" % (line, column, fmt)) % args)


class Scanner(object):
    """
    This class enables the tokenization of the old plist formats which are essentially
    JSON with comments.  To use the scanner simply do: ::


        scanner = Scanner(<string_or_stream>)
        for token in scanner.tokenize():
            user_token(token)

    Ideally this class will not have to be called, instead use the Parser
    for to return a parsed plist stream.
    """
    def __init__(self, string_or_stream):
        self.instream = string_or_stream
        if type(self.instream) in (str, unicode):
            self.instream = cStringIO.StringIO()
            self.instream.write(string_or_stream)
            self.instream.reset()
        self.line = 0
        self.column = 0
        self.incomment = False
        self.started_identifier = False
        self.currtoken = ""

    def next_char(self):
        ch = self.instream.read(1)
        if ch == '\n':
            self.column = 0
            self.line += 1
        else:
            self.column += 1
        return ch

    def make_error(self, fmt, *args):
        self.started_identifier = False
        self.currtoken = ""
        return Token(TOKEN_ERROR, (fmt % args))

    def tokenize(self):
        """
        A scanner for a plist string or stream.

        >>> list(Scanner("3").tokenize())
        [3, END]

        >>> list(Scanner("'3'").tokenize())
        ['3', END]

        >>> list(Scanner("(1)").tokenize())
        [OPEN_LIST, 1, CLOSE_LIST, END]

        >>> list(Scanner("3 4 5").tokenize())
        [3, 4, 5, END]

        >>> list(Scanner("3/*asdfasdf*/5").tokenize())
        [3, 5, END]

        >>> list(Scanner("\\"3/4/5\\"").tokenize())
        ['3/4/5', END]

        >>> list(Scanner("\\\"3/4/5").tokenize())
        [ERROR('Missing "')]

        >>> list(Scanner("hello/world").tokenize())
        [hello/world, END]
        """
        parse_failed = False
        currchar = self.next_char()
        while currchar:
            if self.incomment:
                if currchar == '*':
                    nextchar = self.next_char()
                    if nextchar == '/':
                        self.incomment = False
            else:
                if is_delimiter(currchar):
                    if currchar == '/':   # possible start of a comment
                        nextchar = self.next_char()
                        if nextchar not in "*/":
                            # not a comment so as we were
                            self.currtoken += "/" + nextchar
                        else:   # beginning of a comment
                            if self.currtoken and self.started_identifier:
                                self.started_identifier = False
                                yield self.make_value_token()
                            if nextchar == '/':
                                # skip till end of line
                                self.instream.readline()
                                self.column = 0
                                self.line += 1
                            elif nextchar == '*':
                                self.incomment = True
                    elif self.currtoken and self.started_identifier:
                        self.started_identifier = False
                        yield self.make_value_token()

                    if currchar == ';':
                        yield Token(TOKEN_SEMICOLON)
                    elif currchar == ',':
                        yield Token(TOKEN_COMA)
                    elif currchar == '=':
                        yield Token(TOKEN_EQUALS)
                    elif currchar == '{':
                        yield Token(TOKEN_OPEN_DICT)
                    elif currchar == '(':
                        yield Token(TOKEN_OPEN_LIST)
                    elif currchar == '}':
                        yield Token(TOKEN_CLOSE_DICT)
                    elif currchar == ')':
                        yield Token(TOKEN_CLOSE_LIST)
                    elif currchar == '"' or currchar == "'":  # start of quoted string
                        startchar = currchar
                        self.currtoken = currchar
                        currchar = self.next_char()
                        while currchar and currchar != startchar:
                            if currchar == "\\":
                                self.currtoken += currchar
                                currchar = self.next_char()
                            self.currtoken += currchar
                            currchar = self.next_char()
                        if currchar != startchar:
                            yield self.make_error("Missing %s" % startchar)
                            parse_failed = True
                        else:
                            self.currtoken += startchar
                            yield Token(TOKEN_STRING, eval(self.currtoken))
                    elif currchar.isspace():
                        # do nothing
                        pass
                else:
                    if not self.started_identifier:
                        self.currtoken = ""
                        self.started_identifier = True
                    self.currtoken += currchar
            currchar = self.next_char()
        if self.currtoken and self.started_identifier:
            self.started_identifier = False
            yield self.make_value_token()
        if not parse_failed:
            yield Token(TOKEN_END)

    def make_value_token(self):
        if False and self.currtoken.isdigit():
            return Token(TOKEN_NUMBER, int(self.currtoken))
        else:
            return Token(TOKEN_IDENTIFIER, self.currtoken)


class Token(object):
    def __init__(self, toktype, value=None):
        self.toktype = toktype
        self.value = value

    def __eq__(self, other):
        othertype = type(other)
        if othertype == Token:
            return self.toktype == other.toktype and self.value == other.value
        elif othertype in (str, unicode):
            return self.value == other

    def __hash__(self):
        if self.value:
            return hash(self.toktype + ":" + self.value)
        else:
            return hash(self.toktype)

    def __repr__(self):
        if self.value:
            if self.toktype == TOKEN_NUMBER:
                return "'%s'" % self.value
            elif self.toktype == TOKEN_STRING:
                return "'%s'" % self.value
            elif self.toktype == TOKEN_ERROR:
                return "ERROR('%s')" % self.value
            else:
                return "%s" % self.value
        else:
            return "%s" % (self.toktype.replace("TOKEN_", ""))

    def startswith(self, prefix): return self.value.startswith(prefix)

    def endswith(self, suffix): return self.value.endswith(suffix)


class PlistDict(dict):
    """
    Overides to ensure that identifier Tokens are hashable by their value.
    """
    def __getitem__(self, key):
        if not super(PlistDict, self).__contains__(key):
            if type(key) is Token:
                key = key.value
            elif type(key) in (str, unicode):
                key = Token(TOKEN_IDENTIFIER, key)
        return super(PlistDict, self).__getitem__(key)

    def __contains__(self, key):
        keytype = type(key)
        contains = super(PlistDict, self).__contains__(key)
        if not contains:
            if keytype is Token:
                contains = super(PlistDict, self).__contains__(key.value)
            elif keytype in (str, unicode):
                contains = super(PlistDict, self).__contains__(Token(TOKEN_IDENTIFIER, key))
        return contains

    def strkeys(self):
        return [k.value for k in self.keys()]
