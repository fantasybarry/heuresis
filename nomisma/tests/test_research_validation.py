from copy import deepcopy
from datetime import date, timedelta
import unittest

from nomisma.research_validation import audit_replay, simultaneous_session_bounds


class FunnelTests(unittest.TestCase):
    def fixture(self):
        return {'config': {'costs': {'entry_slippage': .001}}, 'decisions': [
            {'id': 'd', 'session_date': '2026-09-03', 'eligible': True,
             'alert_level': 'Buy', 'disposition': 'order', 'blockers': []}],
            'orders': [{'id': 'o', 'decision_id': 'd', 'symbol': 'TE', 'status': 'expired',
                        'filled_quantity': 0, 'plan': {'levels': {'entry_trigger': 4.49, 'entry_max': 4.49}}}]}

    def test_empty_slippage_adjusted_interval(self):
        report = audit_replay(self.fixture())
        self.assertEqual(report['orders'][0]['ask_max_inclusive'], '4.489')
        self.assertEqual(report['total']['structurally_unfillable_orders'], 1)

    def test_inclusive_equal_boundary_is_feasible(self):
        data = self.fixture(); data['orders'][0]['plan']['levels']['entry_max'] = 4.491
        self.assertEqual(audit_replay(data)['orders'][0]['classification'], 'feasible_interval_unfilled')

    def test_impossible_fill_rejected(self):
        data = self.fixture(); data['orders'][0]['filled_quantity'] = 1
        with self.assertRaises(ValueError): audit_replay(data)


class InferenceTests(unittest.TestCase):
    def fixture(self):
        days = [(date(2025, 1, 1)+timedelta(days=i)).isoformat() for i in range(40)]
        base = [{'date': day, 'session_return': (-.01, .02, .003, -.004)[i % 4],
                 'valid': True, 'opened_trades': 1} for i, day in enumerate(days)]
        panel = {'a': base, 'b': deepcopy(base)}
        folds = [{'id': 'f1', 'validation_dates': days[:20]}, {'id': 'f2', 'validation_dates': days[20:]}]
        spec = {'alpha': .05, 'replicates': 500, 'block_length': 5, 'seed': 20260918,
                'min_complete_blocks': 8, 'min_active_blocks': 3, 'baseline_id': 'a'}
        return panel, folds, spec

    def test_paired_identical_policy_and_repeat(self):
        args = self.fixture(); report = simultaneous_session_bounds(*args)
        self.assertEqual(report, simultaneous_session_bounds(*args))
        self.assertEqual(report['policies'][0]['mean_interval'], report['policies'][1]['mean_interval'])
        self.assertEqual(report['policies'][1]['baseline_mean_difference'], 0)
        self.assertIsNone(report['selected_config'])

    def test_column_order_invariant(self):
        panel, folds, spec = self.fixture()
        self.assertEqual(simultaneous_session_bounds(panel, folds, spec),
                         simultaneous_session_bounds(dict(reversed(list(panel.items()))), folds, spec))

    def test_missing_or_nonfinite_not_zero_filled(self):
        for kind in ('missing', 'nan', 'invalid'):
            panel, folds, spec = self.fixture()
            if kind == 'missing': panel['b'].pop()
            elif kind == 'nan': panel['b'][0]['session_return'] = float('nan')
            else: panel['b'][0]['valid'] = False
            with self.assertRaises(ValueError): simultaneous_session_bounds(panel, folds, spec)

    def test_overlapping_folds_rejected(self):
        panel, folds, spec = self.fixture()
        folds[1]['validation_dates'][0] = folds[0]['validation_dates'][-1]
        with self.assertRaises(ValueError): simultaneous_session_bounds(panel, folds, spec)

    def test_sparse_activity_has_no_interval(self):
        panel, folds, spec = self.fixture()
        for row in panel['b'][1:]: row['opened_trades'] = 0
        report = simultaneous_session_bounds(panel, folds, spec)
        self.assertEqual(report['status'], 'insufficient_evidence')
        self.assertIsNone(report['simultaneous_halfwidth'])

    def test_short_folds_rejected_as_evidence(self):
        panel, folds, spec = self.fixture()
        folds = [{'id': 'short', 'validation_dates': folds[0]['validation_dates'][:2]}]
        panel = {key: rows[:2] for key, rows in panel.items()}
        self.assertIsNone(simultaneous_session_bounds(panel, folds, spec)['simultaneous_halfwidth'])

    def test_fold_length_weighting(self):
        panel, folds, spec = self.fixture()
        folds[0]['validation_dates'] = [row['date'] for row in panel['a'][:10]]
        folds[1]['validation_dates'] = [row['date'] for row in panel['a'][10:]]
        for rows in panel.values():
            for i, row in enumerate(rows): row['session_return'] = .02 if i < 10 else -.01
        report = simultaneous_session_bounds(panel, folds, spec)
        self.assertAlmostEqual(report['policies'][0]['mean_session_return'], -.0025)
        self.assertEqual(report['status'], 'insufficient_evidence')
        self.assertIsNone(report['simultaneous_halfwidth'])

    def test_degenerate_blocks_do_not_emit_exact_confidence(self):
        panel, folds, spec = self.fixture()
        spec['block_length'] = 4
        # Each four-session circular block has identical sum despite varying days.
        report = simultaneous_session_bounds(panel, folds, spec)
        self.assertEqual(report['status'], 'insufficient_evidence')
        self.assertIsNone(report['simultaneous_halfwidth'])


if __name__ == '__main__': unittest.main()
