#!/usr/bin/env python3
"""Gom usage cua Claude Code tren may nay -> CSV trong repo -> push len git.

Chay lai bao nhieu lan cung ra ket qua giong nhau: moi lan quet lai toan bo
transcript va ghi de dong tuong ung. Bo mot ngay khong chay thi lan sau tu bu.
"""
import argparse
import csv
import glob
import io
import json
import os
import platform
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(REPO, "data")
SUMMARY = os.path.join(REPO, "SUMMARY.md")
COLUMNS = ["machine", "date", "project", "session", "agent", "model",
           "input", "output", "cache_write_5m", "cache_write_1h", "cache_read", "cost_usd"]
# Ten cot token trung ten khoa gia trong pricing.json -> tinh cost bang mot vong lap.
NUMERIC = ["input", "output", "cache_write_5m", "cache_write_1h", "cache_read"]
LEGACY_CACHE_WRITE = "cache_write"          # schema cu gop 5m + 1h vao mot cot
KEY = ["machine", "date", "project", "session", "agent", "model"]

# ---- TAM THOI TAT PUSH -------------------------------------------------
# True  = chi ghi CSV + SUMMARY.md, tuyet doi khong dung toi git (khong
#         fetch, khong reset, khong rebase, khong commit, khong push).
# False = chay binh thuong. Doi lai False khi da kiem tra xong so lieu.
PUSH_DISABLED = False
# ------------------------------------------------------------------------


# ---------------------------------------------------------------- thu thap

def config_dirs():
    """Chi doc tai khoan mac dinh ~/.claude.

    May co the co nhieu profile (~/.claude-personal, ~/.claude-work...) va bien
    CLAUDE_CONFIG_DIR co the dang tro sang profile khac - co tinh khong dung toi.
    """
    path = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    return [path] if os.path.isdir(path) else []


def basename_any(path):
    """cwd co the la duong dan Windows doc tren may khac -> tach ca hai kieu dau gach."""
    return re.split(r"[\\/]", path.rstrip("\\/"))[-1] if path else ""


def slugify(path):
    """Claude Code dat ten thu muc session bang cach doi moi ky tu la thanh '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path)


def load_pricing():
    with open(os.path.join(REPO, "pricing.json"), encoding="utf-8") as f:
        data = json.load(f)
    return data["models"], data.get("web_search_per_request", 0.01)


def rate_for(model, models, fast):
    """Khop ten model, bo duoi ngay thang (claude-haiku-4-5-20251001 -> claude-haiku-4-5)."""
    rate = models.get(model)
    if rate is None:
        for name in sorted(models, key=len, reverse=True):
            if model.startswith(name + "-"):
                rate = models[name]
                break
    if rate is None:
        return None
    return rate.get("fast", rate) if fast else rate


def tokens_of(usage):
    """Tach cache write theo TTL - hai muc gia khac nhau nen phai luu rieng.

    Ban ghi khong co dict `cache_creation` la dinh dang cu: Claude Code khi do ghi
    cache TTL 1h, nen don het vao 1h (da doi chieu voi ban ghi cost-state).
    """
    cc = usage.get("cache_creation") or {}
    return {
        "input": usage.get("input_tokens", 0),
        "output": usage.get("output_tokens", 0),
        "cache_write_5m": cc.get("ephemeral_5m_input_tokens", 0) if cc else 0,
        "cache_write_1h": (cc.get("ephemeral_1h_input_tokens", 0) if cc
                           else usage.get("cache_creation_input_tokens", 0)),
        "cache_read": usage.get("cache_read_input_tokens", 0),
    }


def cost_of(vals, usage, rate, ws_price):
    ws = (usage.get("server_tool_use") or {}).get("web_search_requests", 0)
    return sum(vals[name] * rate[name] for name in NUMERIC) / 1e6 + ws * ws_price


def scan(machine, verbose=False):
    """Doc het transcript, gop theo (ngay, project, session, agent, model)."""
    models, ws_price = load_pricing()
    ctx = {
        "calls": {},         # (message id, requestId) -> {"rec": ..., "sessions": {...}}
        "unknown": set(),
        "session_cwd": {},   # session -> (do uu tien, timestamp, cwd)
    }
    files = sub = 0
    for projects in config_dirs():
        # Subagent nam sau vai cap: <project>/<session>/subagents/workflows/<wf>/agent-*.jsonl
        for path in glob.glob(os.path.join(projects, "**", "*.jsonl"), recursive=True):
            files += 1
            if os.sep + "subagents" + os.sep in path:
                sub += 1
            scan_file(path, projects, ctx, models, ws_price)

    # Resume/fork tao session id moi nhung chep lai ca lich su cu, nen mot luot goi
    # co the mang nhieu session id. Session nao it luot nhat trong so do la session goc
    # da thuc su goi no; cac ban chep chi giu phan rieng cua minh.
    dem = defaultdict(int)
    for call in ctx["calls"].values():
        for name in call["sessions"]:
            dem[name] += 1

    rows = defaultdict(lambda: defaultdict(float))
    for call in ctx["calls"].values():
        luc, fallback, agent, model, vals, cost = call["rec"]
        session = min(call["sessions"], key=lambda x: (dem[x], x)) if call["sessions"] else ""
        cwd = (ctx["session_cwd"].get(session) or (None, None, None))[2]
        add_row(rows, (machine, luc.strftime("%Y-%m-%d"),
                       basename_any(cwd) or fallback, session, agent, model), vals, cost)

    if verbose:
        print("  quet %d file transcript (%d cua subagent), %d luot goi API"
              % (files, sub, len(ctx["calls"])))
    if ctx["unknown"]:
        warn("chua co gia cho model: %s -> cost=0" % ", ".join(sorted(ctx["unknown"])))
    return rows


def scan_file(path, projects, ctx, models, ws_price):
    unknown = ctx["unknown"]
    folder = os.path.relpath(path, projects).split(os.sep)[0]   # thu muc project, ke ca file long sau
    fallback_project = folder.split("-")[-1]

    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if '"usage"' not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("type") != "assistant":
                continue
            msg = rec.get("message") or {}
            usage = msg.get("usage") or {}
            model = msg.get("model")
            if not model or model == "<synthetic>" or not usage:
                continue

            stamp = rec.get("timestamp")
            if not stamp:
                continue
            session = rec.get("sessionId") or ""
            # cwd troi theo lenh cd trong phien. Thu muc dung ten cua session moi la goc
            # that su; cwd nao khop ten thu muc do thi uu tien, khong thi lay cai som nhat.
            if rec.get("cwd"):
                rank = 0 if slugify(rec["cwd"]) == folder else 1
                old = ctx["session_cwd"].get(session)
                if old is None or (rank, stamp) < old[:2]:
                    ctx["session_cwd"][session] = (rank, stamp, rec["cwd"])

            # Mot luot goi API bi ghi thanh nhieu dong (moi content block mot dong) va
            # con bi chep lai o file khac khi session duoc resume.
            key = ((msg.get("id"), rec.get("requestId"))
                   if (msg.get("id") or rec.get("requestId")) else rec.get("uuid"))
            call = ctx["calls"].get(key)
            if call is not None:
                call["sessions"].add(session)
                continue

            local = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()
            rate = rate_for(model, models, usage.get("speed") == "fast")
            if rate is None:
                unknown.add(model)
            vals = tokens_of(usage)
            # Ban ghi cua subagent tu khai loai agent; nhanh chinh thi khong co truong nay.
            agent = rec.get("attributionAgent") or ("subagent" if rec.get("isSidechain") else "main")
            ctx["calls"][key] = {
                "rec": (local, fallback_project, agent, model, vals,
                        cost_of(vals, usage, rate, ws_price) if rate else 0.0),
                "sessions": {session},
            }


def add_row(rows, key, vals, cost):
    bucket = rows[key]
    for name in NUMERIC:
        bucket[name] += vals[name]
    bucket["cost"] += cost


# ------------------------------------------------------------------- CSV

def read_csv_rows(path, keys=None):
    if not os.path.exists(path):
        return {}
    out = {}
    shown = (os.path.relpath(path, REPO).replace("\\", "/")
             if os.path.abspath(path).startswith(REPO + os.sep) else path)
    with open(path, newline="", encoding="utf-8-sig") as fh:
        legacy = False
        for lineno, row in enumerate(csv.DictReader(fh), start=2):
            try:
                key = tuple(row[c] for c in (keys or KEY))
                vals = {name: float(row.get(name) or 0) for name in NUMERIC}
                if row.get("cache_write_5m") is None and row.get(LEGACY_CACHE_WRITE):
                    # Schema cu khong ghi TTL -> don vao 1h, dung cach script cu tinh gia.
                    vals["cache_write_1h"] = float(row[LEGACY_CACHE_WRITE])
                    legacy = True
                vals["cost"] = float(row.get("cost_usd") or 0)
            except (KeyError, TypeError, ValueError) as err:
                # Dong hong ma bo im lang thi so lieu tut di khong ai biet -> phai keu.
                warn("%s dong %d: bo qua dong hong (%s)" % (shown, lineno, err))
                continue
            out[key] = vals
        if legacy:
            warn("%s dung schema cu (cot %s) - da coi toan bo la TTL 1h"
                 % (shown, LEGACY_CACHE_WRITE))
    return out


def read_rows_of(machine):
    rows = {}
    for path in sorted(glob.glob(os.path.join(DATA, machine, "*.csv"))):
        rows.update(read_csv_rows(path))
    return rows


def read_all_machines():
    rows = {}
    for path in sorted(glob.glob(os.path.join(DATA, "*", "*.csv"))):
        rows.update(read_csv_rows(path))
    return rows


def write_machine_csv(machine, merged):
    """Ghi lai tung file thang cua rieng may nay. May khac khong dung toi -> khong bao gio conflict."""
    by_month = defaultdict(dict)
    for key, vals in merged.items():
        by_month[key[1][:7]][key] = vals
    changed = []
    for month, items in sorted(by_month.items()):
        path = os.path.join(DATA, machine, month + ".csv")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        before = ""
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                before = fh.read()
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")   # ten project co the chua dau phay
        writer.writerow(COLUMNS)
        for key in sorted(items):
            vals = items[key]
            writer.writerow(list(key) + [int(vals[name]) for name in NUMERIC]
                            + ["%.6f" % vals["cost"]])
        text = "\ufeff" + buf.getvalue()                # BOM de Excel doc tieng Viet khong loi font
        if text != before:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            changed.append(os.path.relpath(path, REPO).replace("\\", "/"))
    return changed


# --------------------------------------------------------------- SUMMARY

def human(n):
    for unit, div in (("b", 1e9), ("m", 1e6), ("k", 1e3)):
        if n >= div:
            return "%.1f%s" % (n / div, unit)
    return str(int(n))


def cache_write_total(vals):
    return vals["cache_write_5m"] + vals["cache_write_1h"]


def totals_row(vals, cost_bold=False):
    money = format(vals["cost"], ",.2f")
    return "%s | %s | %s | %s | %s" % (
        human(vals["input"]), human(vals["output"]), human(vals["cache_read"]),
        human(cache_write_total(vals)), ("**$%s**" % money) if cost_bold else money)


def write_summary(rows):
    per_machine = defaultdict(lambda: defaultdict(float))
    per_day = defaultdict(lambda: defaultdict(float))          # (ngay, may)
    per_model = defaultdict(lambda: defaultdict(float))
    per_project = defaultdict(lambda: defaultdict(float))      # (may, project)
    span, sessions, days, active = {}, defaultdict(set), set(), defaultdict(set)

    for (machine, date, project, session, _agent, model), vals in rows.items():
        days.add(date)
        active[machine].add(date)
        for group in (machine, (machine, project), (date, machine)):
            sessions[group].add(session)
        for bucket, key in ((per_machine, machine), (per_day, (date, machine)),
                            (per_model, model), (per_project, (machine, project))):
            for name in NUMERIC:
                bucket[key][name] += vals[name]
            bucket[key]["cost"] += vals["cost"]
        first, last = span.get(machine, ("9999-99-99", ""))
        span[machine] = (min(first, date), max(last, date))

    machines = sorted(per_machine)
    now = datetime.now().astimezone()
    report = now.strftime("%Y-%m-%d")       # bao cao dung ngay dang chay, gio may
    out = ["# Claude Code usage", "",
           "_Cap nhat: %s (%s) - du lieu goc: `data/<may>/<thang>.csv`_" % (
               now.strftime("%Y-%m-%d %H:%M"), now.strftime("%z")), "",
           "## Ngay %s" % report, "",
           "| May | Session | Input | Output | Cache read | Cache write | Cost (USD) |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    day_total = defaultdict(float)
    for machine in machines:
        vals = per_day.get((report, machine))
        if not vals:
            out.append("| %s | - | - | - | - | - | - |" % machine)   # may nay chua co so lieu hom nay
            continue
        out.append("| **%s** | %d | %s |" % (
            machine, len(sessions[(report, machine)]), totals_row(vals, cost_bold=True)))
        for name in NUMERIC + ["cost"]:
            day_total[name] += vals[name]
    if len(machines) > 1:
        out.append("| _Tat ca_ | %d | %s |" % (
            sum(len(sessions[(report, m)]) for m in machines), totals_row(day_total, True)))

    today = sorted(((k, v) for k, v in rows.items() if k[1] == report),
                   key=lambda kv: -kv[1]["cost"])
    if not today:
        out += ["", "Chua co hoat dong nao trong ngay %s." % report]
    else:
        out += ["", "### Chi tiet ngay %s" % report, "",
                "| May | Project | Session | Agent | Model | Input | Output | Cache read | Cache write | Cost (USD) |",
                "|---|---|---|---|---|---:|---:|---:|---:|---:|"]
        for (machine, _date, project, session, agent, model), vals in today:
            out.append("| %s | `%s` | `%s` | %s | `%s` | %s | %s | %s | %s | %s |" % (
                machine, project, session[:8], agent, model,
                human(vals["input"]), human(vals["output"]), human(vals["cache_read"]),
                human(cache_write_total(vals)), format(vals["cost"], ",.2f")))

    out += ["", "## Cost theo ngay (30 ngay co dung gan nhat, USD)", "",
            "| Ngay | " + " | ".join(machines) + " | Tong |",
            "|---|" + "---:|" * (len(machines) + 1)]
    for date in sorted(days)[-30:]:
        cells = [per_day[(date, m)]["cost"] for m in machines]
        out.append("| %s | %s | **%s** |" % (
            date, " | ".join(format(c, ",.2f") if c else "-" for c in cells),
            format(sum(cells), ",.2f")))

    out += ["", "## Cong don ca ky", "",
            "| May | Tu ngay | Den ngay | Ngay dung | Session | Input | Output | Cache read | Cache write | Cost (USD) |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    total = defaultdict(float)
    for machine in machines:
        vals = per_machine[machine]
        out.append("| **%s** | %s | %s | %d | %d | %s |" % (
            machine, span[machine][0], span[machine][1], len(active[machine]),
            len(sessions[machine]), totals_row(vals, cost_bold=True)))
        for name in NUMERIC + ["cost"]:
            total[name] += vals[name]
    out.append("| _Tat ca_ | %s | %s | %d | %d | %s |" % (
        min(days), max(days), len(days), sum(len(sessions[m]) for m in machines),
        totals_row(total, cost_bold=True)))

    out += ["", "### Theo model (ca ky)", "",
            "| Model | Input | Output | Cache read | Cache write | Cost (USD) |",
            "|---|---:|---:|---:|---:|---:|"]
    for model in sorted(per_model, key=lambda m: -per_model[m]["cost"]):
        out.append("| `%s` | %s |" % (model, totals_row(per_model[model])))

    out.append("")

    text = "\n".join(out)
    before = ""
    if os.path.exists(SUMMARY):
        with open(SUMMARY, encoding="utf-8") as fh:
            before = fh.read()
    # Bo dong "Cap nhat" khi so sanh de khong tao commit rong moi lan chay.
    if strip_stamp(text) == strip_stamp(before):
        return False
    with open(SUMMARY, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return True


def strip_stamp(text):
    return "\n".join(l for l in text.splitlines() if not l.startswith("_Cap nhat:"))


# ------------------------------------------------------------------- git

def git(*args, **kw):
    check = kw.get("check", True)
    proc = subprocess.run(["git", "-C", REPO] + list(args), capture_output=True, text=True)
    if check and proc.returncode:
        raise RuntimeError("git %s:\n%s%s" % (" ".join(args), proc.stdout, proc.stderr))
    return proc


def branch():
    name = git("rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    return name if name and name != "HEAD" else "main"


def dirty_outside_data():
    """Script chi duoc dung toi data/ va SUMMARY.md - file khac dang sua do thi dung lai.

    Bo qua khac biet chi nam o ky tu xuong dong: repo checkout tren Windows la CRLF
    trong khi index la LF, neu khong bo qua thi task chet oan moi lan chay.
    """
    seen = set()
    for extra in ([], ["--cached"]):
        proc = git("-c", "core.quotepath=false", "diff", "--name-only",
                   "--ignore-cr-at-eol", *extra)
        seen.update(proc.stdout.splitlines())
    return sorted(p for p in (x.strip().strip('"') for x in seen)
                  if p and not p.startswith("data/") and p != "SUMMARY.md")


def sync(machine, fresh, message):
    bad = dirty_outside_data()
    if bad:
        print("Dung lai: dang co thay doi chua commit ngoai data/ -> " + ", ".join(bad[:5]))
        return 1

    push = None
    for attempt in range(1, 4):
        keep = read_rows_of(machine)                   # dong da ghi nhung chua kip push
        branch_name = branch()
        online = git("fetch", "origin", check=False).returncode == 0
        remote = "origin/" + branch_name
        if online and git("rev-parse", "--verify", "--quiet", remote, check=False).returncode:
            # Nhanh nay chua co tren remote - khong co gi de dong bo, push se tu tao.
            print("Chua co %s tren remote - bo qua buoc dong bo, se push tao nhanh moi." % remote)
        elif online:
            ahead = git("rev-list", "--count", "%s..HEAD" % remote, check=False)
            count = ahead.stdout.strip()
            # rev-list that bai tra ve stdout rong; coi rong la "0 commit ahead" thi se
            # reset --hard va xoa mat commit chua push -> phai dung lai.
            if ahead.returncode or not count.isdigit():
                print("Khong doc duoc so commit ahead so voi %s - dung lai, chua dong gi." % remote)
                return 1
            if count == "0":
                git("reset", "--hard", remote)
            else:
                # Co commit chua push (co the la cua nguoi dung) -> rebase, tuyet doi khong reset.
                if git("rebase", remote, check=False).returncode:
                    git("rebase", "--abort", check=False)
                    print("Rebase dinh conflict - dung lai de xu ly tay, chua dong gi.")
                    return 1

        merged = read_rows_of(machine)                 # ban dang co tren remote
        merged.update(keep)
        merged.update(fresh)                           # log tren may la nguon dung nhat
        changed = write_machine_csv(machine, merged)
        write_summary(read_all_machines())

        git("add", "-A", "data", "SUMMARY.md")
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print("Khong co gi moi.")
            return 0
        git("commit", "-m", message)
        if not online:
            print("Fetch that bai (mat mang?) - da commit local, lan chay sau se push.")
            return 0
        push = git("push", "origin", "HEAD:" + branch(), check=False)
        if push.returncode == 0:
            print("Da push: " + (", ".join(changed) or "SUMMARY.md"))
            return 0
        print("Push bi tu choi (lan %d), dong bo lai roi thu tiep..." % attempt)
    print("Push that bai 3 lan:\n" + push.stdout + push.stderr)
    return 1


# ------------------------------------------------------------------ main

def machine_name(arg):
    name = (arg or os.environ.get("CLAUDE_USAGE_MACHINE") or "").strip()
    if not name:
        marker = os.path.join(REPO, ".machine")
        if os.path.exists(marker):
            with open(marker, encoding="utf-8") as fh:
                name = fh.read().strip()
    return re.sub(r"[^A-Za-z0-9._-]+", "-", name or platform.node() or "unknown")


def log_line(text):
    """Task Scheduler / cron chay am tham -> luu lai dau vet de con biet duong dieu tra."""
    try:
        with open(os.path.join(REPO, ".run.log"), "a", encoding="utf-8") as fh:
            fh.write("%s  %s\n" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), text))
    except OSError:
        pass


def warn(text):
    """Task chay am tham: canh bao phai vao ca console lan .run.log moi co nguoi thay."""
    print("CANH BAO: " + text)
    log_line("CANH BAO: " + text)


def main():
    ap = argparse.ArgumentParser(description="Gom usage Claude Code cua may nay va push len git.")
    ap.add_argument("--machine", help="Ten may (mac dinh: file .machine hoac hostname)")
    ap.add_argument("--no-push", action="store_true", help="Chi ghi CSV + SUMMARY, khong dung git")
    ap.add_argument("--dry-run", action="store_true", help="Chi in so lieu, khong ghi file")
    args = ap.parse_args()

    machine = machine_name(args.machine)
    print("May: %s - repo: %s" % (machine, REPO))
    rows = scan(machine, verbose=True)
    if not rows:
        print("Khong tim thay transcript nao trong ~/.claude*/projects")
        return 1
    dates = sorted({key[1] for key in rows})
    print("  %d dong - %s -> %s - $%s" % (
        len(rows), dates[0], dates[-1], format(sum(v["cost"] for v in rows.values()), ",.2f")))

    if args.dry_run:
        for key in sorted(rows)[-10:]:
            vals = rows[key]
            print("   ", " | ".join(key), "|", int(vals["input"]), int(vals["output"]),
                  "$%.4f" % vals["cost"])
        return 0

    tat_push = PUSH_DISABLED and not args.no_push
    if args.no_push or PUSH_DISABLED:
        if tat_push:
            print("PUSH DANG TAT (PUSH_DISABLED = True trong tools/claude_usage.py)"
                  " - chi ghi CSV + SUMMARY, khong dung toi git.")
        merged = read_rows_of(machine)
        merged.update(rows)
        print("Ghi: " + (", ".join(write_machine_csv(machine, merged)) or "(khong doi)"))
        write_summary(read_all_machines())
        if tat_push:
            # Task chay am tham: phai co dau vet, khong thi tuong da push ma thuc ra chua.
            log_line("%s: %d dong den %s, $%s -> GHI LOCAL (push dang tat)" % (
                machine, len(rows), dates[-1],
                format(sum(v["cost"] for v in rows.values()), ",.2f")))
        return 0

    code = sync(machine, rows, "%s: usage den %s" % (machine, datetime.now().strftime("%Y-%m-%d")))
    log_line("%s: %d dong den %s, $%s -> %s" % (
        machine, len(rows), dates[-1], format(sum(v["cost"] for v in rows.values()), ",.2f"),
        "OK" if code == 0 else "LOI"))
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:                      # noqa: BLE001 - task chay am tham, phai ghi lai loi
        log_line("LOI: %s" % err)
        raise
