"""Minimum-cost perfect assignment (Hungarian / Kuhn-Munkres, O(n^3)).

Pure Python, no dependencies outside the standard library, so it can be
unit-tested without FreeCAD.
"""

INF = float("inf")


def solve(cost):
    """Return the minimum-cost perfect assignment of a square cost matrix.

    ``cost`` is an n×n list of lists of comparable numbers. The result is a
    list ``col_of_row`` where ``col_of_row[i]`` is the column assigned to
    row ``i``; the sum ``cost[i][col_of_row[i]]`` over all rows is minimal.
    Ties are broken arbitrarily.

    Implementation: Jonker-Volgenant flavour of the Hungarian algorithm with
    row potentials, O(n^3).
    """
    n = len(cost)
    if n == 0:
        return []
    if any(len(row) != n for row in cost):
        raise ValueError("cost matrix must be square, got rows of %s"
                         % sorted({len(row) for row in cost}))

    # 1-based arrays following the classic formulation.
    u = [0.0] * (n + 1)         # row potentials
    v = [0.0] * (n + 1)         # column potentials
    match = [0] * (n + 1)       # match[j] = row matched to column j (0 = free)
    way = [0] * (n + 1)         # back-pointer through the alternating tree

    for i in range(1, n + 1):
        match[0] = i
        j0 = 0
        minv = [INF] * (n + 1)  # reduced-cost minima per column
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = match[j0]
            delta = INF
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[match[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if match[j0] == 0:
                break
        # augment: flip the found alternating path
        while j0:
            j1 = way[j0]
            match[j0] = match[j1]
            j0 = j1

    col_of_row = [0] * n
    for j in range(1, n + 1):
        col_of_row[match[j] - 1] = j - 1
    return col_of_row


def total_cost(cost, col_of_row):
    """Sum of a solution returned by :func:`solve` (test/debug helper)."""
    return sum(cost[i][j] for i, j in enumerate(col_of_row))
