"""Per-domain exclusive cost share from a WRF rsl.error.0000.

WRF's 'Timing for main ... on domain N' elapsed time is INCLUSIVE of that
domain's nests, so the exclusive cost of domain N is
    sum(elapsed on N) - sum(elapsed on N+1)
over the same model-time window.

Handles both timing-line formats: adaptive time stepping prints '(dt= X)',
a fixed time step does not, so model time is taken from the timestamps.
"""
import re, sys, collections
from datetime import datetime

PAT = re.compile(
    r"Timing for main(?: \(dt=\s*[0-9.]+\))?: time (\S+) on domain\s+(\d+):\s+([0-9.]+) elapsed")


def load(path):
    rows = []
    for t, d, el in PAT.findall(open(path, errors="ignore").read()):
        try:
            ts = datetime.strptime(t[:19], "%Y-%m-%d_%H:%M:%S")
        except ValueError:
            continue
        rows.append((ts, int(d), float(el)))
    return rows


def report(path, label=""):
    rows = load(path)
    if not rows:
        print(f"{label}no timing lines"); return
    d1 = [r for r in rows if r[1] == 1]
    if len(d1) < 3:
        print(f"{label}only {len(d1)} d01 steps -- too few to profile"); return

    # window bounded by complete d01 steps, dropping the first (init/IO)
    lo, hi = d1[1][0], d1[-1][0]
    win = [r for r in rows if lo <= r[0] <= hi]
    model = (hi - lo).total_seconds()

    incl, nstep = collections.defaultdict(float), collections.Counter()
    for ts, d, el in win:
        incl[d] += el
        nstep[d] += 1
    total = incl[min(incl)]

    print(f"{label}{'dom':>4} {'steps':>7} {'excl s':>9} {'share':>7} {'s/step':>8}")
    for d in sorted(incl):
        excl = incl[d] - incl.get(d + 1, 0.0)
        print(f"{label}d0{d} {nstep[d]:>7} {excl:>9.1f} {100*excl/total:>6.1f}% "
              f"{incl[d]/nstep[d]:>8.3f}")
    print(f"{label}-> {model:.0f} s model in {total:.0f} s wall = "
          f"{total/model:.3f} wall-s per model-s")
    return total / model


if __name__ == "__main__":
    if len(sys.argv) > 2:
        res = {}
        for a in sys.argv[1:]:
            n = int(re.search(r"n(\d+)", a).group(1)) if re.search(r"n(\d+)", a) else a
            print(f"===== {n} ranks =====")
            r = report(a, "  ")
            if r: res[n] = r
            print()
        if len(res) > 1:
            base = max(res)           # compare against the largest rank count
            print(f"{'ranks':>6} {'wall/model':>11} {'vs 8 ranks':>11} {'par eff':>8}")
            ref = res.get(min(res))
            for n in sorted(res):
                sp = ref / res[n]
                print(f"{n:>6} {res[n]:>11.3f} {sp:>11.2f}x "
                      f"{100*sp/(n/min(res)):>7.0f}%")
    else:
        report(sys.argv[1])
