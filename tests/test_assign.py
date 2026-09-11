"""Hungarian solver tests: brute-force cross-validation + edge cases.

Pure standard library; run with any python3:
    python3 -m unittest test_assign -v
"""

import itertools
import random
import unittest

from freecad.RibLoft import assign


def brute_force(cost):
    n = len(cost)
    best, best_perm = None, None
    for perm in itertools.permutations(range(n)):
        c = sum(cost[i][perm[i]] for i in range(n))
        if best is None or c < best:
            best, best_perm = c, list(perm)
    return best_perm


class TestSolve(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(assign.solve([]), [])

    def test_single(self):
        self.assertEqual(assign.solve([[7.0]]), [0])

    def test_known(self):
        # cheap diagonal beats the expensive one
        cost = [[1, 100], [100, 1]]
        self.assertEqual(assign.solve(cost), [0, 1])
        cost = [[100, 1], [1, 100]]
        self.assertEqual(assign.solve(cost), [1, 0])
        cost = [[0, 1], [1, 0]]
        self.assertEqual(assign.solve(cost), [0, 1])
        # tie -> any perfect assignment; check cost only
        cost = [[5, 5], [5, 5]]
        self.assertEqual(assign.total_cost(cost, assign.solve(cost)), 10)

    def test_brute_force_cross_validation(self):
        rng = random.Random(42)
        for trial in range(300):
            n = rng.randint(1, 7)
            cost = [[float(rng.randint(-50, 50)) for _ in range(n)]
                    for _ in range(n)]
            got = assign.solve(cost)
            self.assertEqual(sorted(got), list(range(n)),
                             "not a permutation: %s" % got)
            self.assertEqual(
                assign.total_cost(cost, got),
                assign.total_cost(cost, brute_force(cost)),
                "suboptimal for n=%d cost=%r got=%s" % (n, cost, got))

    def test_random_floats_permutation_and_bound(self):
        rng = random.Random(7)
        for trial in range(20):
            n = rng.randint(8, 30)
            cost = [[rng.random() * 1000 for _ in range(n)] for _ in range(n)]
            got = assign.solve(cost)
            self.assertEqual(sorted(got), list(range(n)))
            # never worse than the identity and the reversed assignments
            self.assertLessEqual(assign.total_cost(cost, got),
                                 assign.total_cost(cost, list(range(n))))
            self.assertLessEqual(
                assign.total_cost(cost, got),
                assign.total_cost(cost, list(reversed(range(n)))))

    def test_rectangular_raises(self):
        with self.assertRaises(ValueError):
            assign.solve([[1, 2, 3], [4, 5, 6]])

    def test_symmetric_metric_semantics(self):
        # cost[i][j] = |i - j| -> optimal is identity
        n = 6
        cost = [[abs(i - j) for j in range(n)] for i in range(n)]
        self.assertEqual(assign.solve(cost), list(range(n)))
        # cost[i][j] = |i - (n-1-j)| -> optimal is the reversal
        cost = [[abs(i - (n - 1 - j)) for j in range(n)] for i in range(n)]
        self.assertEqual(assign.solve(cost), list(reversed(range(n))))


if __name__ == "__main__":
    unittest.main(verbosity=2)
