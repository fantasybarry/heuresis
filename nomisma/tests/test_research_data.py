"""Offline bounds, immutable event provenance, and minute-only preflight tests."""
from datetime import date,timedelta
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import itertools

from nomisma import research_data as data


def calendar():
    start=date(2026,4,1)
    return [{'date':(start+timedelta(days=i)).isoformat(),'open':'09:30','close':'16:00'}
            for i in range(180) if (start+timedelta(days=i)).weekday()<5]


def requester(url,params,headers):
    if url.endswith('/calendar'):return calendar()
    if url.endswith('/clock'):return {'timestamp':'2026-09-18T14:00:00Z','is_open':True}
    if url.endswith('/assets'):return [{'symbol':'TE','status':'active'}]
    if url.endswith('/corporate-actions'):return {'corporate_actions':{},'next_page_token':None}
    day=params['asof'];symbols=params['symbols'].split(',')
    if params['timeframe']=='1Day':
        prior=[r['date'] for r in calendar() if params['start'][:10]<=r['date']<day]
        bars=[{'t':d+'T04:00:00Z','o':2,'h':2.1,'l':1.9,'c':2,'v':1000} for d in prior]
    else:
        # A deliberate gap at13:51 leaves a21minute prefix and a later21window.
        stamps=[f'{day}T13:{minute:02d}:00Z' for minute in range(30,60) if minute!=51]
        stamps += [f'{day}T14:{minute:02d}:00Z' for minute in range(15)]
        bars=[{'t':t,'o':2,'h':2.1,'l':1.9,'c':2,'v':1000,'vw':2,'n':3} for t in stamps]
    return {'bars':{symbol:bars for symbol in symbols},'next_page_token':None}


class ResearchDataTests(unittest.TestCase):
    def test_receipts_preserve_raw_versions_and_hash_chain(self):
        original=[{'T':'b','S':'TE','t':'2026-09-18T14:00:00Z','c':2},
                  {'T':'u','S':'TE','t':'2026-09-18T14:00:00Z','c':2.1},
                  {'T':'c','S':'TE','t':'2026-09-18T14:01:00.123456789Z','oi':1,'ci':2},
                  {'T':'x','S':'TE','t':'2026-09-18T14:01:00Z','i':2}]
        def stream(symbols,event,stop,status):
            status('connecting');status('live')
            event({'T':'nomisma_subscription','required':True,'statuses':False,'lulds':True})
            for item in original:event(item)
            stop.wait(1)
        with tempfile.TemporaryDirectory() as temp:
            path=data.record_session(temp,['TE'],duration_seconds=.02,stream=stream)
            result=data.verify_recording(path)
            self.assertTrue(result['verified']);self.assertEqual(result['status'],'complete_bounded_capture')
            rows=[json.loads(line) for line in (Path(temp)/'events.jsonl').read_text().splitlines()]
            self.assertEqual([r['payload'] for r in rows if r['kind'] in ('b','u','c','x')],original)
            self.assertEqual(result['counts']['u'],1)
            self.assertFalse(result['coverage_complete'])

    def test_tamper_and_overwrite_rejected(self):
        def stream(symbols,event,stop,status):status('live');stop.wait(1)
        with tempfile.TemporaryDirectory() as temp:
            path=data.record_session(temp,['TE'],duration_seconds=.01,stream=stream)
            events=Path(temp)/'events.jsonl';events.write_bytes(events.read_bytes().replace(b'recorder_start',b'recorder_wrong'))
            with self.assertRaisesRegex(ValueError,'hash chain'):
                data.verify_recording(path)
            with self.assertRaisesRegex(ValueError,'immutable'):
                data.record_session(temp,['TE'],duration_seconds=.01,stream=stream)

    def test_event_budget_and_reconnect_gap_are_explicit(self):
        attempts=[]
        def stream(symbols,event,stop,status):
            attempts.append(1);status('live')
            if len(attempts)==1:raise OSError('arbitrary-secret-looking-text')
            for _ in range(20):event({'T':'q','S':'TE','t':'2026-09-18T14:00:00Z','bp':2,'ap':2.1})
        with tempfile.TemporaryDirectory() as temp:
            path=data.record_session(temp,['TE'],duration_seconds=2,max_events=8,stream=stream)
            manifest=json.loads(path.read_bytes());verified=data.verify_recording(path)
            self.assertEqual(manifest['status'],'incomplete');self.assertEqual(manifest['termination'],'event_limit')
            self.assertEqual(manifest['attempts'],2);self.assertTrue(manifest['gaps'])
            self.assertEqual(verified['records'],8)
            self.assertNotIn('arbitrary-secret-looking-text',(Path(temp)/'events.jsonl').read_text())

    def test_connection_limit_does_not_reconnect_or_touch_monitor(self):
        def stream(symbols,event,stop,status):
            raise ValueError('Alpaca stream: connection limit exceeded; stop other sessions using this feed.')
        with tempfile.TemporaryDirectory() as temp:
            path=data.record_session(temp,['TE'],duration_seconds=1,stream=stream)
            manifest=json.loads(path.read_bytes())
            self.assertEqual(manifest['attempts'],1)
            self.assertEqual(manifest['termination'],'stream_connection_limit')
            self.assertEqual(manifest['status'],'incomplete')

    def test_failed_initial_attempt_preserves_entire_initial_gap(self):
        attempts=[]
        def stream(symbols,event,stop,status):
            attempts.append(1)
            if len(attempts)==1:raise OSError('first attempt failed')
            status('live');stop.wait(1)
        with tempfile.TemporaryDirectory() as temp:
            path=data.record_session(temp,['TE'],duration_seconds=.55,stream=stream)
            manifest=json.loads(path.read_bytes());result=data.verify_recording(path)
            rows=[json.loads(line) for line in (Path(temp)/'events.jsonl').read_text().splitlines()]
            live=next(row for row in rows if row['kind']=='transport_status' and row['payload']['state']=='live')
            self.assertEqual(result['attempts'],2)
            self.assertEqual(len(result['gaps']),1)
            gap=result['gaps'][0]
            self.assertEqual(gap['start_unix_ns'],manifest['started_at_ns'])
            self.assertEqual(gap['start_monotonic_ns'],manifest['started_monotonic_ns'])
            self.assertEqual(gap['end_unix_ns'],live['receipt_unix_ns'])
            self.assertEqual(gap['end_monotonic_ns'],live['receipt_monotonic_ns'])
            self.assertEqual(gap['start_attempt_id'],0)
            self.assertEqual(gap['end_attempt_id'],2)

    def test_all_attempts_failed_gap_and_manifest_tampering(self):
        def stream(symbols,event,stop,status):raise OSError('not persisted')
        with tempfile.TemporaryDirectory() as temp:
            path=data.record_session(temp,['TE'],duration_seconds=2,stream=stream)
            original=json.loads(path.read_bytes());verified=data.verify_recording(path)
            self.assertEqual(verified['status'],'incomplete')
            self.assertEqual(original['termination'],'attempts_exhausted')
            self.assertEqual(original['gaps'][0]['start_monotonic_ns'],original['started_monotonic_ns'])
            self.assertEqual(original['gaps'][0]['end_monotonic_ns'],original['ended_monotonic_ns'])
            for key,value in (('gaps',[]),('attempts',1),('status','complete_bounded_capture'),
                              ('started_monotonic_ns',original['started_monotonic_ns']+1)):
                with self.subTest(key=key):
                    changed=dict(original);changed[key]=value;path.write_text(json.dumps(changed))
                    with self.assertRaisesRegex(ValueError,'transport/coverage'):
                        data.verify_recording(path)
            path.write_text(json.dumps(original))

    def test_trailing_gap_uses_exact_hashed_disconnect_receipt(self):
        def stream(symbols,event,stop,status):
            status('live');raise OSError('connection lost')
        with tempfile.TemporaryDirectory() as temp:
            path=data.record_session(temp,['TE'],duration_seconds=1,max_attempts=1,stream=stream)
            manifest=json.loads(path.read_bytes());verified=data.verify_recording(path)
            rows=[json.loads(line) for line in (Path(temp)/'events.jsonl').read_text().splitlines()]
            disconnected=next(row for row in rows if row['kind']=='transport_disconnected')
            trailing=verified['gaps'][-1]
            self.assertEqual(trailing['start_unix_ns'],disconnected['receipt_unix_ns'])
            self.assertEqual(trailing['start_monotonic_ns'],disconnected['receipt_monotonic_ns'])
            self.assertEqual(trailing['end_monotonic_ns'],manifest['ended_monotonic_ns'])

    def test_wall_clock_regression_preserves_monotonic_gap_evidence(self):
        def stream(symbols,event,stop,status):status('live');stop.wait(1)
        with tempfile.TemporaryDirectory() as temp:
            walls=itertools.count(10**18,-100)
            with patch.object(data.time,'time_ns',side_effect=lambda:next(walls)):
                path=data.record_session(temp,['TE'],duration_seconds=.01,stream=stream)
            verified=data.verify_recording(path)
            self.assertGreater(verified['wall_clock_regressions'],0)
            gap=verified['gaps'][0]
            self.assertGreaterEqual(gap['end_monotonic_ns'],gap['start_monotonic_ns'])
            self.assertLess(gap['end_unix_ns'],gap['start_unix_ns'])

    def test_preflight_freezes_dates_before_bars_and_records_gaps(self):
        with tempfile.TemporaryDirectory() as temp:
            def checked(url,params,headers):
                if url.endswith('/bars'):
                    self.assertTrue((Path(temp)/'registration.json').exists())
                self.assertNotIn('/quotes',url);self.assertNotIn('/trades',url)
                return requester(url,params,headers)
            path=data.acquire_preflight(temp,['TE'],session_count=2,end_date='2026-09-02',requester=checked)
            manifest=json.loads(path.read_bytes());registration=json.loads((Path(temp)/'registration.json').read_bytes())
            self.assertEqual(manifest['status'],'complete');self.assertEqual(manifest['requests'],7)
            self.assertEqual(registration['session_dates'],['2026-09-01','2026-09-02'])
            stats=next(r for r in manifest['sessions'][0]['stats'] if r['symbol']=='TE')
            self.assertEqual(stats['from_open_contiguous_minutes'],21)
            self.assertGreater(stats['rolling_21_minute_windows'],stats['from_open_decisions_with_21_bars'])
            self.assertEqual(stats['missing_rth_slots'],346)
            self.assertFalse(manifest['historical_universe_established'])
            self.assertTrue(manifest['not_execution_dataset'])

    def test_preflight_request_budget_preserves_failure_and_registration(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'budget exhausted'):
                data.acquire_preflight(temp,['TE'],session_count=2,max_requests=1,requester=requester)
            manifest=json.loads((Path(temp)/'manifest.json').read_bytes())
            self.assertEqual(manifest['status'],'incomplete');self.assertEqual(manifest['requests'],1)
            self.assertTrue((Path(temp)/'registration.json').exists())

    def test_byte_budget_prevents_payload_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'byte budget'):
                data.acquire_preflight(temp,['TE'],session_count=1,max_bytes=10,requester=requester)
            manifest=json.loads((Path(temp)/'manifest.json').read_bytes())
            self.assertEqual(manifest['status'],'incomplete');self.assertEqual(manifest['pages'],[])

    def test_metadata_get_allowlist_and_optional_access_denial(self):
        calls=[]
        def limited(url,params,headers):
            calls.append(url)
            if url.endswith('/corporate-actions'):
                raise ValueError('Historical data request failed (HTTP 403).')
            return requester(url,params,headers)
        with tempfile.TemporaryDirectory() as temp:
            path=data.capture_metadata(temp,['TE'],requester=limited)
            manifest=json.loads(path.read_bytes())
            self.assertEqual(manifest['status'],'complete_with_unavailable_metadata')
            self.assertEqual(manifest['unavailable'][0]['reason'],'http_403')
            self.assertEqual(len(calls),5)
            self.assertTrue(all(url.endswith(('/clock','/calendar','/assets','/corporate-actions')) for url in calls))
            self.assertIn('retrieval only',manifest['universe_basis'])


if __name__=='__main__':unittest.main()
