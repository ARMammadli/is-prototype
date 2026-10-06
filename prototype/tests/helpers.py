from sim.roster import Roster
from sim.ward import Nurse, Ward


def make_ward(n=4, days=14, seniors=None, night_ok=None, demand=None, fte=1.0):
    seniors = seniors if seniors is not None else [True] * n
    night_ok = night_ok if night_ok is not None else [True] * n
    nurses = [Nurse(f"Nurse_{i + 1:02d}", fte, seniors[i], night_ok[i]) for i in range(n)]
    available = {(x.id, d) for x in nurses for d in range(days)}
    return Ward(nurses, days, demand or {"D": 1, "E": 1, "N": 1}, set(), available)


def roster_with(ward, assignments):
    r = Roster(ward)
    for nid, items in assignments.items():
        for d, s in items.items():
            r.assign(nid, d, s)
    return r
