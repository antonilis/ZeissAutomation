"""
How a Windows program splits its command line into argv, so that a test can follow the
arguments PythonAnalysisRunner builds all the way into World B's sys.argv.

On the microscope PC the runner joins its arguments into ONE string (Process.StartInfo.Arguments)
and python.exe's C runtime splits it again. The rules are those of the Microsoft C runtime
("Parsing C++ command-line arguments", learn.microsoft.com), which CommandLineToArgvW shares:

- arguments are separated by spaces or tabs;
- a double quote opens or closes a quoted part, in which spaces do not separate;
- 2n backslashes followed by a quote become n backslashes, and the quote opens or closes;
- 2n+1 backslashes followed by a quote become n backslashes and a literal quote;
- backslashes not followed by a quote are literal;
- inside a quoted part, two quotes in a row are one literal quote;
- the first argument, the program name, ends at the first space outside quotes and knows
  no backslash escapes.

tests/contract/test_cli_roundtrip.py checks this module against the examples of that page.
"""


def _program_name(line):
    i, n, quoted, out = 0, len(line), False, []
    while i < n:
        c = line[i]
        if c == '"':
            quoted = not quoted
        elif c in " \t" and not quoted:
            break
        else:
            out.append(c)
        i += 1
    return "".join(out), i


def split(line):
    """
    :param str line: the whole command line, program name first
    :return: list of str, argv as the C runtime builds it
    """
    argv = []
    program, i = _program_name(line)
    argv.append(program)

    n = len(line)
    while True:
        while i < n and line[i] in " \t":
            i += 1
        if i >= n:
            break

        arg, quoted = [], False
        while i < n:
            c = line[i]
            if c == "\\":
                start = i
                while i < n and line[i] == "\\":
                    i += 1
                count = i - start
                if i < n and line[i] == '"':
                    arg.append("\\" * (count // 2))
                    if count % 2:
                        arg.append('"')
                        i += 1
                    # an even count leaves the quote to the branch below, unconsumed
                else:
                    arg.append("\\" * count)
                continue
            if c == '"':
                if quoted and i + 1 < n and line[i + 1] == '"':
                    arg.append('"')
                    i += 2
                    continue
                quoted = not quoted
                i += 1
                continue
            if c in " \t" and not quoted:
                break
            arg.append(c)
            i += 1

        argv.append("".join(arg))

    return argv
