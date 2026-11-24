#!/usr/bin/env python3
"""Snapshot de isolamento para o benchmark TASK 02 (somente leitura do sistema).

Registra caminho, tamanho, mtime e SHA-256 de:
  - todo o conteúdo de tasks/flipt-task02/ (exceto saídas de execução, ver EXCLUDE);
  - arquivos de configuração e histórico compartilhados do Pi em ~/.pi/agent;
  - a lista (sem hash) de ~/.pi/agent/sessions, que é o diretório padrão de sessões.

Uso:
  python scripts/snapshot.py take OUT.json
  python scripts/snapshot.py compare ANTES.json DEPOIS.json [--allow PREFIXO ...] [--out DIFF.json]

`compare` sai com código 2 se houver alteração fora dos prefixos permitidos.
Não restaura nem exclui nada: apenas registra divergências.

Limite: isolamento por verificação, não sandbox de segurança. Leituras não são
detectadas (mtime não registra leitura); só alterações de conteúdo ou metadados.
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

TASK_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HOME_AGENT = os.path.join(os.path.expanduser("~"), ".pi", "agent")

# Saídas de execução são gravadas pelo próprio wrapper e registradas em result.json.
# Artefatos de controle gravados por estas ferramentas (não são alterações do agente):
# pi-rust-build: artefatos de compilação; a identidade do binário é o SHA-256 registrado no manifesto.
EXCLUDE_DIRS = {"evaluator/work", "evaluator/results", "evidence/infra-tests", "evidence/preparation/pi-rust-build"}
EXCLUDE_PREFIXES = ("evidence/preparation/snapshot-", "evidence/preparation/isolation-check-")
EXCLUDE_NAMES = {"index", "index.lock"}  # .git/index muda com git status (metadado do git)

EXTERNAL_FILES = [
    "auth.json", "settings.json", "models.json", "models-store.json",
    "prompt-history.jsonl", "crashes.json",
]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _rel(path, root=None):
    return os.path.relpath(path, root or TASK_ROOT).replace("\\", "/")


def _skip(path, root=None):
    """True para caminhos excluídos: evaluator/work e evidence/<agente>/runs/**."""
    rel = _rel(path, root)
    for d in EXCLUDE_DIRS:
        if rel == d or rel.startswith(d + "/"):
            return True
    if rel.startswith(EXCLUDE_PREFIXES):
        return True
    parts = rel.split("/")
    if "__pycache__" in parts:
        return True
    if len(parts) >= 4 and parts[0] == "evidence" and parts[2] == "runs":
        return True
    return False


def take(root=None, home_agent=None):
    # resolvidos na chamada (não na importação), para respeitar redirecionamento de caminhos
    root = root or TASK_ROOT
    home_agent = home_agent or HOME_AGENT
    entries = {}
    for dirpath, dirnames, filenames in os.walk(root):
        # poda diretórios excluídos antes de descer
        dirnames[:] = [d for d in dirnames if not _skip(os.path.join(dirpath, d), root)]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if name in EXCLUDE_NAMES or name.endswith(".lock") or _skip(full, root):
                continue
            try:
                st = os.stat(full, follow_symlinks=False)
            except OSError as e:
                entries[_rel(full, root)] = {"error": str(e)}
                continue
            entries[_rel(full, root)] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns,
                                       "sha256": _sha256(full)}
    # arquivos externos compartilhados
    for name in EXTERNAL_FILES:
        full = os.path.join(home_agent, name)
        key = "ext:" + name
        if os.path.isfile(full):
            st = os.stat(full)
            entries[key] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": _sha256(full)}
        else:
            entries[key] = {"absent": True}
    # diretório padrão de sessões: somente metadados (arquivos podem ser grandes)
    sess = os.path.join(home_agent, "sessions")
    if os.path.isdir(sess):
        for dirpath, _, filenames in os.walk(sess):
            for name in filenames:
                full = os.path.join(dirpath, name)
                st = os.stat(full)
                rel = "ext:sessions/" + os.path.relpath(full, sess).replace("\\", "/")
                entries[rel] = {"size": st.st_size, "mtime_ns": st.st_mtime_ns, "meta_only": True}
    return {"taken_utc": _now(), "root": root, "home_agent": home_agent, "entries": entries}


def compare(before, after, allow_prefixes):
    b, a = before["entries"], after["entries"]
    changes = []
    for key in sorted(set(b) | set(a)):
        if key not in a:
            kind = "removed"
        elif key not in b:
            kind = "added"
        elif b[key] != a[key]:
            kind = "modified"
        else:
            continue
        allowed = any(key == p or key.startswith(p) for p in allow_prefixes)
        changes.append({"path": key, "change": kind, "allowed": allowed,
                        "before": b.get(key), "after": a.get(key)})
    divergences = [c for c in changes if not c["allowed"]]
    return {"compared_utc": _now(), "changes": changes, "divergences": divergences,
            "allow_prefixes": allow_prefixes, "ok": not divergences}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("take")
    t.add_argument("out")
    c = sub.add_parser("compare")
    c.add_argument("before")
    c.add_argument("after")
    c.add_argument("--allow", action="append", default=[])
    c.add_argument("--out")
    args = p.parse_args(argv)
    if args.cmd == "take":
        snap = take()
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
        print(f"snapshot: {len(snap['entries'])} entradas -> {args.out}")
        return 0
    with open(args.before, encoding="utf-8") as f:
        before = json.load(f)
    with open(args.after, encoding="utf-8") as f:
        after = json.load(f)
    result = compare(before, after, args.allow)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
    print(f"mudancas={len(result['changes'])} divergencias={len(result['divergences'])}")
    for d in result["divergences"]:
        print(f"  DIVERGENCIA {d['change']}: {d['path']}")
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    sys.exit(main())
