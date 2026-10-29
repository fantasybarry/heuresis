"""Research diagnostics; neither parameter selection nor a trading service.

The block bootstrap is an approximate, conditional uncertainty calculation.
Its screening thresholds are declared engineering criteria, not a proof of
statistical adequacy. Incomplete panels and overlapping validation folds fail
closed. Insufficient sampling screens produce no confidence interval.
"""

from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
import math
import random


def audit_replay(result):
    """Retain every decision/order and distinguish impossible entry intervals."""
    buckets = defaultdict(Counter)
    blockers, reasons, dispositions = Counter(), Counter(), Counter()
    decisions = result['decisions']
    by_id = {row['id']: row for row in decisions}
    if len(by_id) != len(decisions):
        raise ValueError('Decision identifiers must be unique.')
    for row in decisions:
        stats = buckets[row['session_date']]
        stats['decisions'] += 1
        stats['eligible'] += bool(row['eligible'])
        stats['alerts'] += bool(row.get('alert_level'))
        blockers.update(row.get('blockers', []))
        dispositions[row['disposition']] += 1
        reasons.update(row.get('plan', {}).get('reasons', []))
    slip = Decimal(str(result['config']['costs']['entry_slippage']))
    if not slip.is_finite() or slip < 0:
        raise ValueError('Finite nonnegative entry slippage is required.')
    orders = []
    for order in result['orders']:
        decision = by_id[order['decision_id']]
        levels = order['plan']['levels']
        lower = Decimal(str(levels['entry_trigger']))
        upper = Decimal(str(levels['entry_max'])) - slip
        if not lower.is_finite() or not upper.is_finite():
            raise ValueError('Finite entry levels are required.')
        empty = lower > upper
        filled = order.get('filled_quantity', 0) > 0
        if empty and filled:
            raise ValueError('Fill contradicts the frozen ask admissibility contract.')
        stats = buckets[decision['session_date']]
        stats['orders'] += 1
        stats['orders_with_fills'] += filled
        stats['expired_orders'] += order['status'] == 'expired'
        stats['structurally_unfillable_orders'] += empty
        classification = ('empty_admissible_ask_interval' if empty else
                          'filled' if filled else 'feasible_interval_unfilled')
        orders.append({'id': order['id'], 'symbol': order['symbol'],
                       'date': decision['session_date'], 'status': order['status'],
                       'ask_min_inclusive': str(lower), 'ask_max_inclusive': str(upper),
                       'classification': classification,
                       'filled_quantity': order.get('filled_quantity', 0)})
    return {'schema_version': 1, 'kind': 'retrospective_execution_funnel',
            'per_session': [{'date': day, **dict(stats)} for day, stats in sorted(buckets.items())],
            'total': dict(sum(buckets.values(), Counter())),
            'decision_dispositions': dict(dispositions),
            'nonexclusive_blocker_counts': dict(blockers.most_common()),
            'nonexclusive_plan_reason_counts': dict(reasons.most_common()),
            'orders': orders,
            'limits': ['Blocker counts overlap and do not establish causal attribution.',
                       'A nonempty price interval does not establish liquidity or fill probability.',
                       'This diagnostic does not change frozen entry, tick, cost or signal rules.']}


def simultaneous_session_bounds(panel, folds, spec):
    """Paired circular blocks within each disjoint validation fold.

    panel: {policy_id: [{date, session_return, valid, opened_trades}, ...]}.
    folds: [{id, validation_dates: [...]}]. Training dates are not consumed.
    All candidates must have exactly the same registered validation dates.
    """
    required = {'alpha', 'replicates', 'block_length', 'seed',
                'min_complete_blocks', 'min_active_blocks', 'baseline_id'}
    if not isinstance(spec, dict) or required - set(spec):
        raise ValueError('A complete inference specification is required.')
    alpha, reps, length = spec['alpha'], spec['replicates'], spec['block_length']
    if (type(alpha) not in (int, float) or not 0 < alpha < 1 or
            type(reps) is not int or reps < 100 or type(length) is not int or length < 1 or
            type(spec['seed']) is not int or type(spec['min_complete_blocks']) is not int or
            spec['min_complete_blocks'] < 1 or type(spec['min_active_blocks']) is not int or
            spec['min_active_blocks'] < 1):
        raise ValueError('Invalid registered inference controls.')
    if not panel or not all(isinstance(key, str) and key for key in panel):
        raise ValueError('Nonempty policy IDs are required.')
    ids = sorted(panel)
    if spec['baseline_id'] not in ids:
        raise ValueError('Registered baseline is absent from the family.')
    dates, fold_indexes, fold_ids = [], [], set()
    for fold in folds:
        days = fold.get('validation_dates')
        if (not isinstance(fold.get('id'), str) or not fold['id'] or fold['id'] in fold_ids or
                not isinstance(days, list) or not days or days != sorted(set(days))):
            raise ValueError('Unique folds with ordered unique validation dates are required.')
        for day in days:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError('Canonical ISO session dates are required.')
        if set(dates) & set(days) or (dates and dates[-1] >= days[0]):
            raise ValueError('Validation folds must be disjoint and chronological.')
        fold_ids.add(fold['id'])
        fold_indexes.append(list(range(len(dates), len(dates) + len(days))))
        dates.extend(days)
    if not dates:
        raise ValueError('At least one validation fold is required.')
    columns, activity = [], []
    for ident in ids:
        rows = panel[ident]
        mapped = {row['date']: row for row in rows}
        if len(mapped) != len(rows) or set(mapped) != set(dates):
            raise ValueError('Every candidate must have exactly the same complete validation panel.')
        values, counts = [], []
        for day in dates:
            row = mapped[day]
            value = row.get('session_return')
            count = row.get('opened_trades')
            if (row.get('valid') is not True or type(value) not in (int, float) or
                    not math.isfinite(value) or type(count) is not int or count < 0):
                raise ValueError('Missing, invalid or nonfinite return/activity cannot be zero-filled.')
            values.append(float(value)); counts.append(count)
        columns.append(values); activity.append(counts)
    n = len(dates)
    means = [math.fsum(values) / n for values in columns]
    complete_blocks = [block[i:i+length] for block in fold_indexes
                       for i in range(0, len(block)-length+1, length)]
    active_blocks = [sum(any(counts[i] > 0 for i in block) for block in complete_blocks)
                     for counts in activity]
    blockers = []
    if any(len(block) < 2*length for block in fold_indexes):
        blockers.append('Every validation fold needs at least two declared blocks.')
    if len(complete_blocks) < spec['min_complete_blocks']:
        blockers.append('Too few complete nonoverlapping validation blocks.')
    candidate_blockers = {}
    for j, ident in enumerate(ids):
        issues = []
        if active_blocks[j] < spec['min_active_blocks']:
            issues.append('Too few activity-bearing blocks.')
        if not any(len({columns[j][i] for i in block}) > 1 for block in fold_indexes):
            issues.append('No within-fold session-return variation for resampling.')
        candidate_blockers[ident] = issues
    # Family inference cannot silently remove the unsuccessful or inactive trials.
    if any(candidate_blockers.values()):
        blockers.append('At least one registered candidate fails activity or variation screens.')
    halfwidth = None
    baseline_index = ids.index(spec['baseline_id'])
    if not blockers:
        rng = random.Random(spec['seed'])
        maxima = []
        for unused in range(reps):
            sampled = []
            for block in fold_indexes:
                local = []
                while len(local) < len(block):
                    start = rng.randrange(len(block))
                    local.extend(block[(start+k) % len(block)] for k in range(length))
                sampled.extend(local[:len(block)])
            errors = [math.fsum(values[i] for i in sampled)/n-means[j]
                      for j, values in enumerate(columns)]
            maxima.append(max([abs(error) for error in errors] +
                              [abs(error-errors[baseline_index]) for error in errors]))
        if len(set(maxima)) < 2 or max(maxima) == 0:
            blockers.append('Degenerate bootstrap error distribution; no interval is supported.')
        else:
            maxima.sort()
            halfwidth = maxima[min(reps-1, math.ceil((1-alpha)*reps)-1)]
    rows = []
    for j, ident in enumerate(ids):
        contrast = means[j] - means[baseline_index]
        rows.append({'id': ident, 'mean_session_return': means[j],
                     'active_complete_blocks': active_blocks[j],
                     'candidate_screen_failures': candidate_blockers[ident],
                     'mean_interval': None if halfwidth is None else [means[j]-halfwidth, means[j]+halfwidth],
                     'baseline_mean_difference': contrast,
                     'baseline_difference_interval': None if halfwidth is None else
                         ([0.0, 0.0] if j == baseline_index else [contrast-halfwidth, contrast+halfwidth])})
    return {'schema_version': 1, 'method': 'paired_within_fold_circular_block_max_deviation',
            'interpretation': 'Approximate conditional intervals; dependence/stationarity assumptions required.',
            'specification': dict(spec), 'dates': dates, 'folds': folds,
            'complete_nonoverlapping_blocks': len(complete_blocks),
            'status': 'insufficient_evidence' if blockers else 'conditional_diagnostic_intervals',
            'sampling_screen_failures': blockers, 'simultaneous_halfwidth': halfwidth,
            'policies': rows, 'selected_config': None, 'candidate_for_holdout': None,
            'selection_note': 'Intervals alone do not satisfy economic, risk, stability, data or untouched-holdout gates.'}
