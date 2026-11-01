from itertools import product, groupby
import unittest
import numpy as np
from ..bounds import segment_frontier, pool_bounds
from ..contracts import EvaluationSegment, MODELS
from ..evaluation import compare_pool, primary_sensitivity
from ..markov import forward_backward, end_marginals, causal_forecast, fit_markov
from ..solver import solve_primary
from ..targets import end_labels, marginal_labels


def run_oracle(z, k):
    result = np.zeros(len(z), dtype=int); offset = 0
    for bit, group in groupby(z):
        length = len(list(group)); offset += length
        if bit == 1 and length >= k and offset < len(z):
            result[offset] = 1
    return result


def brute(observations, weights, budget, k):
    sizes = [len(o) for o in observations]; values = []
    for bits in product((0, 1), repeat=sum(sizes)):
        offset = errors = 0; total = 0.0
        for o, w in zip(observations, weights):
            z = np.array(bits[offset:offset+len(o)]); offset += len(o)
            errors += int(np.sum((o >= 0) & (o != z)))
            total += float(w @ run_oracle(z, k))
        if errors <= budget:
            values.append(total)
    return min(values), max(values)


class MathTests(unittest.TestCase):
    def test_END_against_run_boundaries(self):
        for k in (1, 2, 3):
            for bits in product((0, 1), repeat=7):
                np.testing.assert_array_equal(end_labels(bits, k), run_oracle(bits, k))

    def test_DP_exhaustive_missing_and_wrong_observations(self):
        rng = np.random.default_rng(1201)
        for _ in range(14):
            o = rng.integers(-1, 2, size=7); w = rng.normal(size=7); w[:3] = 0
            low, high = segment_frontier(o, w, 3, 2)
            for r in (0, 1, 2):
                expected = brute([o], [w], r, 3)
                self.assertAlmostEqual(float(np.min(low[:r+1])), expected[0])
                self.assertAlmostEqual(float(np.max(high[:r+1])), expected[1])

    def test_global_budget_not_budget_per_segment(self):
        obs = [np.ones(4, dtype=int), np.ones(4, dtype=int)]
        weights = [np.array([0., 0., 0., 1.])]*2
        lo, hi = pool_bounds(obs, weights, 3, 2)
        np.testing.assert_allclose(hi[0], [0, 1, 2])
        for r in (0, 1, 2):
            expected = brute(obs, weights, r, 3)
            np.testing.assert_allclose([lo[0, r], hi[0, r]], expected)

    def test_rectangle_marginals_include_reference_error(self):
        lo0, hi0, known, _ = marginal_labels([1, 1, 1, 0], 3, 0)
        lo1, hi1, _, _ = marginal_labels([1, 1, 1, 0], 3, 1)
        self.assertEqual(known[-1], 1)
        self.assertEqual((lo0[-1], hi0[-1]), (1, 1))
        self.assertEqual((lo1[-1], hi1[-1]), (0, 1))

    def test_Markov_posterior_exhaustive(self):
        a = np.array([[0.8, 0.2], [0.35, 0.65]]); pi = np.array([0.4, 0.6])
        for o in (np.array([-1]*6), np.array([1, -1, 1, 0, -1, 0])):
            total = 0.; expected = np.zeros(6)
            for bits in product((0, 1), repeat=6):
                z = np.array(bits)
                if np.any((o >= 0) & (o != z)):
                    continue
                mass = pi[z[0]] * np.prod(a[z[:-1], z[1:]])
                total += mass; expected += mass*run_oracle(z, 3)
            np.testing.assert_allclose(end_marginals(o, a, pi), expected/total, atol=1e-12)

    def test_causal_forecast_does_not_read_current_or_future(self):
        a = np.array([[0.8, 0.2], [0.35, 0.65]]); pi = np.array([0.4, 0.6])
        o = np.array([1, 1, -1, 0, 1, 0]); changed = o.copy(); changed[3:] = 1
        np.testing.assert_allclose(causal_forecast(o, a, pi)[:4], causal_forecast(changed, a, pi)[:4])

    def test_train_EM_valid_parameters(self):
        a, pi, history = fit_markov([np.array([1, -1, 1, 0, 0, -1, 1])], max_iterations=5)
        np.testing.assert_allclose(a.sum(axis=1), 1); self.assertAlmostEqual(pi.sum(), 1)
        self.assertTrue((a > 0).all() and (pi > 0).all() and np.isfinite(history).all())

    def test_full_control_and_outer_intervals(self):
        rng = np.random.default_rng(40); z = np.array([1, 1, 1, 0, 0, 1, 1, 0])
        p = rng.uniform(0.05, 0.95, size=(6, len(z))); score = np.arange(len(z)) >= 3
        inputs = [EvaluationSegment("x", np.array([str(i) for i in range(len(z))]), z, score, p)]
        rows, points, info = compare_pool(inputs, np.array([[.8, .2], [.3, .7]]), np.array([.5, .5]), .5)
        y = run_oracle(z, 3); risks = ((p[:, score]-y[score])**2).mean(axis=1)
        self.assertEqual(len(rows), 15)
        for row in rows:
            expected = risks[MODELS.index(row['model_a'])]-risks[MODELS.index(row['model_b'])]
            for field in ('joint_lower','joint_upper','rectangle_lower','rectangle_upper','separate_lower','separate_upper'):
                self.assertAlmostEqual(row[field], expected)
        for point in points:
            self.assertAlmostEqual(point['estimated_risk'], risks[MODELS.index(point['model'])])

    def test_sensitivity_matches_generic_solver_and_brute_force(self):
        rng = np.random.default_rng(11)
        segments = []
        for i, o in enumerate((np.array([1, -1, 1, 0, 1]), np.array([1, 1, -1, 1]))):
            p = rng.uniform(.05, .95, (6, len(o))); score = np.arange(len(o)) >= 3
            segments.append(EvaluationSegment(str(i), np.array([f'{i}:{j}' for j in range(len(o))]), o, score, p))
        curve = primary_sensitivity(segments, [0, 1, 2])
        a, b = 1, 0; n = sum(s.score.sum() for s in segments)
        base = sum(((s.probabilities[a]**2-s.probabilities[b]**2)*s.score).sum() for s in segments)/n
        w = [-2*(s.probabilities[a]-s.probabilities[b])*s.score for s in segments]
        for row in curve:
            expected = brute([s.observed for s in segments], w, row['R_global'], 3)
            np.testing.assert_allclose([row['joint_lower'],row['joint_upper']], base+np.asarray(expected)/n)
        for direction in ('min', 'max'):
            result = solve_primary(segments, 1, direction, time_limit=2)
            self.assertEqual(result['status'], 0)
            self.assertTrue(result['witness_valid'])
            expected = curve[1]['joint_lower' if direction == 'min' else 'joint_upper']
            self.assertAlmostEqual(result['incumbent_value'], expected)
            self.assertAlmostEqual(result['conservative_bound'], expected)
