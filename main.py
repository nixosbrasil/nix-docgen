import argparse
import html
import json
import time
import jinja2
import subprocess
from datetime import datetime
from pathlib import Path
import sqlite3
import re
import tarfile
import tempfile
import shutil
from shutil import which
import logging
import sys
import shlex
import time
import bs4

logger = logging.getLogger("nix-docgen")

SCRIPT_DIR = Path(__file__).parent.resolve()

IS_VERBOSE = False
BASE_URL = "http://localhost:1313"

class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels"""
    
    COLORS = {
        'DEBUG': '\033[1m',    # Bold
        'INFO': '\033[34m',    # Blue
        'WARNING': '\033[33m', # Yellow
        'ERROR': '\033[31m',   # Red
        'CRITICAL': '\033[41;37m' # Red background, white text
    }
    RESET = '\033[0m'
    
    LEVEL_SYMBOLS = {
        'DEBUG': 'D',
        'INFO': '*',
        'WARNING': '!',
        'ERROR': 'X',
        'CRITICAL': 'C'
    }
    
    def format(self, record):
        color = self.COLORS.get(record.levelname, '')
        symbol = self.LEVEL_SYMBOLS.get(record.levelname, record.levelname[0])
        record.levelname = f"{color}{symbol}{self.RESET}"
        return super().format(record)


def copy_deep(origin: Path, destination: Path):
    """Copy directory tree from origin to destination using shutil.copy for files"""
    current_copystat = shutil.copystat
    shutil.copystat = lambda x, y: None
    shutil.copytree(origin, destination, copy_function=shutil.copy)
    shutil.copystat = current_copystat


def norm_branch(branch):
    """
    Normalizes the branch name for use in paths/IDs.
    Replaces /, : with -
    """
    return branch.replace('/', '-').replace(':', '-')


def run_subprocess(cmd, capture=True, **kwargs):
    """
    Runs subprocess.run with stderr visible if IS_VERBOSE, otherwise suppresses stderr.
    If capture=True, captures stdout, otherwise passes to sys.stdout.
    Other kwargs are passed normally.
    """
    cmd_str = [str(x) for x in cmd]
    logger.debug(f"Running command: {shlex.join(cmd_str)}")
    if 'stderr' not in kwargs:
        kwargs['stderr'] = None if IS_VERBOSE else subprocess.PIPE
    if 'stdout' not in kwargs:
        kwargs['stdout'] = subprocess.PIPE if capture else None
    ret = subprocess.run(cmd, **kwargs)
    if capture:
        return ret.stdout
    return ret

def build_rev_attribute(rev, attribute):
    ret = run_subprocess([
        "nix", "build", f"nixpkgs/{rev}#{attribute}", '--print-out-paths'
    ], text=True, check=True)
    ret = Path(ret.strip()).resolve()
    assert str(ret).startswith('/nix/store'), ret
    assert ret.exists()
    return ret

def render_template(template, args={}):
    args['baseurl'] = BASE_URL
    args['timestamp'] = int(time.time())
    loader = jinja2.FileSystemLoader(str(SCRIPT_DIR))
    env = jinja2.Environment(loader=loader)
    template = env.get_template(template)
    return template.render(args)

def render_index_html(context):
    return render_template('index.html.jinja', context)


def render_docset_xml(branch):
    return render_template('docset.xml.jinja', {'branch': branch})

def render_info_plist(rev):
    return render_template('Info.plist.jinja', {'rev': rev})


def process_branch_list(branches):
    logger.info(f"Processing branch list: {branches}")
    branches = set(branches)
    if 'stable' in branches:
        logger.info("Replacing 'stable' with the configured stable branch.")
        branches.remove('stable')
        # TODO: proper logic
        branches.add('nixos-25.05')
    return branches

def assert_equal(a, b):
    assert a == b, f"[ASSERTION FAILED] Expected: {b!r}, Got: {a!r} (Returned by function: {a!r})"

assert_equal(process_branch_list(["a", "b"]), {"a", "b"})
assert_equal('stable' not in process_branch_list(["a", "stable"]), True)

def generate_zeal(branch: str, output_file: Path):
    """
    Generates a Zeal/Dash docset from the extracted nixpkgs tree, packaging everything into output_file (.tgz).
    """

    def register_section(DB, key, value, kind="Property"):
        key = key.strip()
        value = value.strip()
        OBJECTS[key] = value
        logger.debug(f"register_section: {kind} {key} {value}")
        DB.execute('INSERT OR IGNORE INTO searchIndex(name, type, path) values (?, ?, ?);', (key, kind, value))


    with tempfile.TemporaryDirectory() as tmpdir:
        docset_root = Path(tmpdir) / 'nixpkgs.docset'
        docset_root.mkdir(parents=True, exist_ok=True)
        (docset_root / "meta.json").write_text(json.dumps({
            "name": "Nixpkgs",
            "revision": branch,
            "title": "Nixpkgs"
        }))
        contents = docset_root / 'Contents'
        resources = contents / 'Resources'
        documents = resources / 'Documents'
        documents.mkdir(parents=True, exist_ok=True)
        index_db = resources / 'docSet.dsidx'
        conn = sqlite3.connect(index_db)
        DB = conn.cursor()
        OBJECTS = {}
        try:
            DB.execute("DROP TABLE searchIndex;")
        except Exception:
            pass
        DB.execute('CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);')
        DB.execute('CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);')

        NIXPKGS_INDEX_FILE = output_file.parent / "nixpkgs" / "index.html" # manual.html is renamed
        NIXPKGS_INDEX = bs4.BeautifulSoup(NIXPKGS_INDEX_FILE.read_text())
        DOC_NAME = "Nixpkgs Manual"
        SECTION_NAME = "Preface"
        for section in NIXPKGS_INDEX.select_one('div.toc').findChildren():
            if section.name == "dt":
                outer_link = section.select_one("a")
                if outer_link is None:
                    continue
                outer_link = str(NIXPKGS_INDEX_FILE.relative_to(output_file.parent).parent) + "/" + outer_link.attrs['href']
                
                SECTION_NAME = section.text
                register_section(DB, f"{DOC_NAME} > {SECTION_NAME}", outer_link, kind="Section")
            if section.name == "dd":
                for item in section.select("span.chapter"):
                    inner_link = item.find("a", recursive=True)
                    inner_link = inner_link.attrs['href']
                    inner_link = str(NIXPKGS_INDEX_FILE.relative_to(output_file.parent).parent) + "/" + inner_link
                    register_section(DB, f"{DOC_NAME} > {SECTION_NAME} > {item.text}", inner_link, kind="Guide")


        NIXOS_INDEX_FILE = output_file.parent / "nixos" / "index.html"
        NIXOS_INDEX = bs4.BeautifulSoup(NIXOS_INDEX_FILE.read_text())
        

        DOC_NAME = "NixOS Manual"
        SECTION_NAME = "Preface"
        for section in NIXOS_INDEX.select_one('div.toc').findChildren():
            if section.name == "dt":
                outer_link = section.select_one("a")
                if outer_link is None:
                    continue
                outer_link = str(NIXOS_INDEX_FILE.relative_to(output_file.parent).parent) + "/" + outer_link.attrs['href']
                
                SECTION_NAME = section.text
                register_section(DB, f"{DOC_NAME} > {SECTION_NAME}", outer_link, kind="Section")
            if section.name == "dd":
                for item in section.select("span.chapter"):
                    inner_link = item.find("a", recursive=True)
                    inner_link = inner_link.attrs['href']
                    inner_link = str(NIXOS_INDEX_FILE.relative_to(output_file.parent).parent) + "/" + inner_link
                    register_section(DB, f"{DOC_NAME} > {SECTION_NAME} > {item.text}", inner_link, kind="Guide")

        DOC_NAME = "NixOS Options"
        NIXOS_OPTIONS_FILE = output_file.parent / "nixos" / "options.html"
        NIXOS_OPTIONS = bs4.BeautifulSoup(NIXOS_OPTIONS_FILE.read_text())
        for section in NIXOS_OPTIONS.select("a.term"):
            option_name = section.text
            outer_link = section
            if outer_link is None:
                continue
            outer_link = str(NIXOS_OPTIONS_FILE.relative_to(output_file.parent).parent) + "/" + outer_link.attrs['href']
            register_section(DB, f"{DOC_NAME} > {option_name}", outer_link, kind="Option")

        conn.commit()
        conn.close()
        (contents / 'Info.plist').write_text(render_info_plist(branch), encoding='utf-8')
        with tarfile.open(output_file, 'w:gz') as tar:
            copy_deep(output_file.parent / "nixpkgs", documents/"nixpkgs")
            copy_deep(output_file.parent / "nixos", documents/"nixos")
            # (documents / "index.html").write_text("<h1>Foi</h1>")
            tar.add(docset_root, arcname='nixpkgs.docset')

def build_branches(branches):
    branches = process_branch_list(branches)
    logger.info(f"Building branches: {branches}")
    target_dir = SCRIPT_DIR / 'target'
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(exist_ok=True)
    
    logger.info(f"Generating index.html at {target_dir / 'index.html'}")
    context = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'branches': [{'name': norm_branch(b)} for b in branches]
    }
    (target_dir / 'index.html').write_text(render_index_html(context), encoding='utf-8')

    for branch in branches:
        norm = norm_branch(branch)
        logger.info(f"Building branch: {branch} (normalized: {norm})")

        nixpkgs_docs = build_rev_attribute(branch, "htmlDocs.nixpkgsManual.x86_64-linux")
        nixos_docs = build_rev_attribute(branch, "htmlDocs.nixosManual.x86_64-linux")
        branch_target = target_dir / norm
        branch_target.mkdir(parents=True, exist_ok=True)
        (target_dir / f"nixpkgs.{branch}.docset.xml").write_text(render_docset_xml(branch))
        for source in [nixpkgs_docs, nixos_docs]:
            doc_dir = (source / "share" / "doc")
            for item in doc_dir.iterdir():
                copy_deep(item, branch_target / item.name)
        NIXPKGS_MANUAL: Path = branch_target / "nixpkgs" / "manual.html"
        if NIXPKGS_MANUAL.exists():
            NIXPKGS_MANUAL.rename(NIXPKGS_MANUAL.parent / "index.html")
        generate_zeal(
            branch, branch_target / "nixpkgs.docset.tgz"
        )


def main():
    global IS_VERBOSE
    global BASE_URL
    parser = argparse.ArgumentParser(description="Generates documentation and docsets for multiple nixpkgs branches.")
    parser.add_argument(
        "branches",
        nargs='+',
        help="List of nixpkgs branches or revisions to process (e.g.: master release-23.05 23.11 or 'stable')"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable detailed logging (DEBUG)"
    )
    parser.add_argument(
        "--base-url", "-b",
        default=BASE_URL,
        help="Base URL for links"
    )
    args = parser.parse_args()
    IS_VERBOSE = args.verbose
    BASE_URL = args.base_url
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='%(levelname)s%(name)s: %(message)s'
    )
    # Apply colored formatter
    for handler in logging.root.handlers:
        handler.setFormatter(ColoredFormatter('%(levelname)s\033[4m%(name)s\033[0m: %(message)s'))
    if not args.branches:
        parser.print_help()
        return
    build_branches(args.branches)


if __name__ == "__main__":
    main()
