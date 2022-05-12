import os, re, sqlite3
from bs4 import BeautifulSoup, NavigableString, Tag
from argparse import ArgumentParser
from pathlib import Path

def interact():
    import code
    code.InteractiveConsole(locals=globals()).interact()

def print_context():
    from sys import argv
    print(argv)

parser = ArgumentParser(description = "Generate Zeal index from nixpkgs html manual")
parser.add_argument("-b", dest = "branch", help = "Branch name", default = "master")
parser.add_argument("--nixpkgs", dest = "nixpkgs", help = "Where the nixpkgs tree is extracted", type = Path, required = True)
parser.add_argument("--output", dest = "output", help = "Where to build the HTML files", type = Path, required = True)
parser.add_argument("--index", dest = "index", help = "Where to generate the index", type = Path, required = True)

args = parser.parse_args()

NIXPKGS = args.nixpkgs
OUT = args.output

conn = sqlite3.connect(args.index)
DB = conn.cursor()
OBJECTS = {}

print(NIXPKGS)
print(OUT)

def register_section(key, value, kind = "Property"):
    key = key.strip()
    value = value.strip()
    OBJECTS[key] = value
    DB.execute('INSERT OR IGNORE INTO searchIndex(name, type, path) values (?, ?, ?);', (key, kind, f"#{key}"))
    print(key, value, kind)

try: DB.execute("DROP TABLE searchIndex;")
except: pass

DB.execute('CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);')
DB.execute('CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);')


def get_lib_sections():
    lib_function_docs = args.nixpkgs / "doc" / "doc-support" / "lib-function-docs.nix"
    ret = []
    with open(str(lib_function_docs), 'r') as f:
        while True:
            line = f.readline()
            if len(line) == 0:
                break
            line = line.strip()
            if line.startswith("docgen"):
                _, key, *value = line.split(' ')
                value = " ".join(value).strip("'")
                ret.append((key, value))
    return ret

def remove_ansi_escape_codes(text):
    # Credits: https://stackoverflow.com/questions/14693701/how-can-i-remove-the-ansi-escape-sequences-from-a-string-in-python
    import re
    ansi_escape = re.compile(r'''
    \x1B  # ESC
    (?:   # 7-bit C1 Fe (except CSI)
        [@-Z\\-_]
    |     # or [ for CSI, followed by a control sequence
        \[
        [0-?]*  # Parameter bytes
        [ -/]*  # Intermediate bytes
        [@-~]   # Final byte
    )
    ''', re.VERBOSE)
    return ansi_escape.sub('', text)

def ingest_lib_documentation(base = "lib", filename = "default.nix"):
    from shutil import which
    from subprocess import run, PIPE
    proc = run([which("nix-doc"), "search", ".*", str(NIXPKGS / "lib" / filename)], stdout = PIPE, stderr = PIPE)
    lines = iter(proc.stdout.decode('utf-8').split("\n"))
    curdoc = ""
    funcname = None
    definedAt = None
    while True:
        try:
            line = next(lines)
            if line.startswith('\x1b[38;5;15;1m'): # is the part that the function gets a name?
                line = remove_ansi_escape_codes(line)
                funcname = line.split('=')[0]
                curdoc = f'{line} \n{curdoc}'
                continue
            if line.startswith('# /nix'):
                line = line[2:]
                definedAt = line
                register_section(
                    f'{base}.{funcname}',
                    f'{curdoc}\nDefined at: {definedAt}',
                    "Function"
                )
                curdoc = ""
                funcname = None
                definedAt = None
                next(lines)
                continue
            curdoc = f'{curdoc}\n{line}'
        except StopIteration:
            break

print(get_lib_sections())
for (section, description) in get_lib_sections():
    print(section, description)
    register_section(
        "lib." + section,
        description,
        "Environment"
    )
    ingest_lib_documentation(base = f'lib.{section}', filename = f'{section}.nix')

conn.commit()
conn.close()

keys = list(OBJECTS.keys())
keys.sort()
with open(str(OUT), 'w') as f:
    from html import escape
    for key in keys:
        f.write(f'<h1 id="{key}">{key}</h1>')
        f.write(f"<pre>{escape(OBJECTS[key])}</pre>\n")
# interact()
