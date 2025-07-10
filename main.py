import argparse
import html
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

# Configuração básica de logging (será ajustada no main)
logger = logging.getLogger("nix-docgen")

SCRIPT_DIR = Path(__file__).parent.resolve()

IS_VERBOSE = False


def norm_branch(branch):
    """
    Normaliza o nome do branch para uso em paths/IDs.
    Substitui /, : por -
    """
    return branch.replace('/', '-').replace(':', '-')


def run_subprocess(cmd, capture=True, **kwargs):
    """
    Executa subprocess.run com stderr visível se IS_VERBOSE, senão suprime stderr.
    Se capture=True, captura stdout, senão passa para sys.stdout.
    Outros kwargs são repassados normalmente.
    """
    cmd_str = [str(x) for x in cmd]
    logger.debug(f"Executando comando: {shlex.join(cmd_str)}")
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


def render_index_html(context):
    """
    Renderiza o template index.html.jinja com o contexto fornecido.
    :param context: dict com as variáveis para o template (ex: generated_at, branches)
    :return: string com o HTML renderizado
    """
    loader = jinja2.FileSystemLoader(str(SCRIPT_DIR))
    env = jinja2.Environment(loader=loader)
    template = env.get_template('index.html.jinja')
    return template.render(context)


def render_info_plist(rev):
    """
    Renderiza o template Info.plist.jinja apenas com o parâmetro rev.
    :param rev: string com o valor do campo rev
    :return: string com o Info.plist renderizado
    """
    loader = jinja2.FileSystemLoader(str(SCRIPT_DIR))
    env = jinja2.Environment(loader=loader)
    template = env.get_template('Info.plist.jinja')
    return template.render(rev=rev)


def process_branch_list(branches):
    logger.info(f"Processando lista de branches: {branches}")
    branches = set(branches)
    if 'stable' in branches:
        logger.info("Substituindo 'stable' pelo branch estável configurado.")
        branches.remove('stable')
        branches.add('nixos-25.05')  # Aqui você pode automatizar a escolha do branch estável
    return branches

def assert_equal(a, b):
    assert a == b, f"[ASSERTION FAILED] Esperado: {b!r}, Obtido: {a!r} (Retornado pela função: {a!r})"

assert_equal(process_branch_list(["a", "b"]), {"a", "b"})
assert_equal('stable' not in process_branch_list(["a", "stable"]), True)

def generate_zeal(branch: str, nixpkgs: Path, output_file: Path):
    """
    Gera um docset Zeal/Dash a partir da árvore nixpkgs extraída, empacotando tudo em output_file (.tgz).
    """
    def remove_ansi_escape_codes(text):
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

    def get_lib_sections(nixpkgs_path):
        lib_function_docs = nixpkgs_path / "doc" / "doc-support" / "lib-function-docs.nix"
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

    def register_section(DB, OBJECTS, key, value, kind="Property"):
        key = key.strip()
        value = value.strip()
        OBJECTS[key] = value
        DB.execute('INSERT OR IGNORE INTO searchIndex(name, type, path) values (?, ?, ?);', (key, kind, f"#{key}"))

    def ingest_lib_documentation(DB, OBJECTS, nixpkgs_path, base="lib", filename="default.nix"):
        lines = run_subprocess([
            "nix", "run", "nixpkgs#nix-doc", "--",
            "search", ".*", str(nixpkgs_path / "lib" / filename)
        ], capture=True, text=True).split('\n')
        lines = iter(lines)
        curdoc = ""
        funcname = None
        definedAt = None
        while True:
            try:
                line = next(lines)
                if line.startswith('\x1b[38;5;15;1m'):
                    line = remove_ansi_escape_codes(line)
                    funcname = line.split('=')[0]
                    curdoc = f'{line} \n{curdoc}'
                    continue
                if line.startswith('# /nix'):
                    line = line[2:]
                    definedAt = line
                    register_section(DB, OBJECTS,
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

    def generate_zeal_index(nixpkgs_path: Path, output_html: Path, index_db: Path, branch: str = "master"):
        conn = sqlite3.connect(index_db)
        DB = conn.cursor()
        OBJECTS = {}
        try:
            DB.execute("DROP TABLE searchIndex;")
        except Exception:
            pass
        DB.execute('CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);')
        DB.execute('CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);')

        for (section, description) in get_lib_sections(nixpkgs_path):
            register_section(DB, OBJECTS, "lib." + section, description, "Environment")
            ingest_lib_documentation(DB, OBJECTS, nixpkgs_path, base=f'lib.{section}', filename=f'{section}.nix')

        conn.commit()
        conn.close()

        keys = list(OBJECTS.keys())
        keys.sort()
        html_content = ""
        for key in keys:
            html_content += f'<h1 id="{key}">{key}</h1>'
            html_content += f"<pre>{html.escape(OBJECTS[key])}</pre>\n"
        output_html.write_text(html_content, encoding='utf-8')

    with tempfile.TemporaryDirectory() as tmpdir:
        docset_root = Path(tmpdir) / 'nixpkgs.docset'
        contents = docset_root / 'Contents'
        resources = contents / 'Resources'
        documents = resources / 'Documents'
        documents.mkdir(parents=True, exist_ok=True)
        # Gera o index do Zeal/Dash (banco e HTML)
        index_db = resources / 'docSet.dsidx'
        output_html = documents / 'index.html'
        generate_zeal_index(
            nixpkgs_path=nixpkgs,
            output_html=output_html,
            index_db=index_db,
            branch=branch
        )
        # Copia Info.plist para dentro do docset
        contents.mkdir(exist_ok=True)
        (contents / 'Info.plist').write_text(render_info_plist(branch), encoding='utf-8')
        # Empacota tudo em tarball
        with tarfile.open(output_file, 'w:gz') as tar:
            tar.add(docset_root, arcname='nixpkgs.docset')

def build_branches(branches):
    branches = process_branch_list(branches)
    logger.info(f"Buildando branches: {branches}")
    target_dir = SCRIPT_DIR / 'target'
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.mkdir(exist_ok=True)
    
    logger.info(f"Gerando index.html em {target_dir / 'index.html'}")
    context = {
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'branches': [{'name': norm_branch(b)} for b in branches]
    }
    (target_dir / 'index.html').write_text(render_index_html(context), encoding='utf-8')

    for branch in branches:
        norm = norm_branch(branch)
        logger.info(f"Buildando branch: {branch} (normalizado: {norm})")

        nixpkgs_docs = build_rev_attribute(branch, "htmlDocs.nixpkgsManual.x86_64-linux")
        nixos_docs = build_rev_attribute(branch, "htmlDocs.nixosManual.x86_64-linux")
        nixpkgs = build_rev_attribute(branch, "path")
        branch_target = target_dir / norm
        branch_target.mkdir(parents=True, exist_ok=True)
        generate_zeal(
            branch, nixpkgs, branch_target / "nixpkgs.docset.tgz"
        )
        for source in [nixpkgs_docs, nixos_docs]:
            doc_dir = (source / "share" / "doc")
            for item in doc_dir.glob('**/*'):
                if item.is_dir():
                    continue
                destination = branch_target / item.relative_to(doc_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.symlink_to(item)


def main():
    global IS_VERBOSE
    parser = argparse.ArgumentParser(description="Gera documentação e docsets para múltiplos branches do nixpkgs.")
    parser.add_argument(
        "branches",
        nargs='+',
        help="Lista de branches ou revisões do nixpkgs para processar (ex: master release-23.05 23.11 ou 'stable')"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Ativa logging detalhado (DEBUG)"
    )
    args = parser.parse_args()
    IS_VERBOSE = args.verbose
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format='[%(levelname)s] %(message)s'
    )
    if not args.branches:
        parser.print_help()
        return
    build_branches(args.branches)


if __name__ == "__main__":
    main()
