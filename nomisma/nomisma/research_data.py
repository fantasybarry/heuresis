"""Bounded read-only research acquisition, separate from all trading services.

Primary references checked 2026-09-18:
https://docs.alpaca.markets/us/docs/real-time-stock-pricing-data
https://docs.alpaca.markets/us/docs/streaming-market-data
https://docs.alpaca.markets/us/reference/get-v2-assets-1
https://docs.alpaca.markets/us/reference/corporateactions-1
https://alpaca.markets/learn/stock-minute-bars

Stream callbacks expose parsed provider payloads, not raw websocket frames.
Receipt timestamps below mean callback acceptance, not network or SIP receipt.
Corporate-action API availability is not guaranteed at announcement time.
Current assets cannot establish historical point-in-time universe membership.
"""

from collections import Counter
from datetime import date, datetime, time as daytime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import threading
import time
from zoneinfo import ZoneInfo

from . import live_data, providers, replay_data
from .replay_data import _canonical, _sha

_NY = ZoneInfo("America/New_York")
_DATA = "https://data.alpaca.markets/v2/stocks/"
_MIB = 1024 * 1024
_EVENTS = frozenset(("t", "q", "b", "u", "d", "c", "x", "s", "l", "nomisma_subscription"))


def _new_directory(path):
    supplied = Path(path).absolute()
    if supplied.is_symlink():
        raise ValueError("Research output cannot be a symbolic link.")
    directory = supplied.resolve()
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise ValueError("Research output must be new or empty; evidence is immutable.")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _write(path, value):
    path.write_bytes(_canonical(value))


def _symbols(symbols):
    if not isinstance(symbols, (list, tuple)) or not 1 <= len(symbols) <= 20:
        raise ValueError("Declare between 1 and 20 fixed symbols; wildcards are unsupported.")
    normalized = [providers._symbol(value) for value in symbols]
    if len(set(normalized)) != len(normalized):
        raise ValueError("Symbols must be unique.")
    return sorted(normalized)


def _error_code(error):
    # Transport errors deliberately expose no provider body or arbitrary text.
    import re
    if str(error) == 'Alpaca stream: connection limit exceeded; stop other sessions using this feed.':
        return 'stream_connection_limit'
    matched = re.fullmatch(r"Historical data request failed \(HTTP (\d{3})\)\.", str(error))
    return "http_" + matched[1] if matched else type(error).__name__


class _Budget:
    def __init__(self, directory, max_requests, max_bytes, requester=None):
        if type(max_requests) is not int or max_requests < 1 or type(max_bytes) is not int or max_bytes < 1:
            raise ValueError("Request and response-byte budgets must be positive integers.")
        if requester is None:
            status, headers, self.account_url = live_data._credentials()
            if status['feed'] != 'sip':
                raise ValueError("This registered research acquisition requires SIP.")
            requester = replay_data._http
        else:
            headers, self.account_url = {}, 'https://paper-api.alpaca.markets'
        self.bytes = self.derived_bytes = 0
        self.max_bytes = max_bytes
        def bounded(url, params, auth):
            result = requester(url, params, auth)
            body = result if isinstance(result, bytes) else _canonical(result)
            if self.bytes + self.derived_bytes + len(body) > max_bytes:
                raise ValueError("Research response-byte budget exhausted; acquisition incomplete.")
            self.bytes += len(body)
            return body
        self.archive = replay_data._Archive(directory, max_requests, bounded, headers)

    def reserve_derived(self, size):
        if self.bytes + self.derived_bytes + size > self.max_bytes:
            raise ValueError('Research retained-payload budget exhausted; acquisition incomplete.')
        self.derived_bytes += size

    def summary(self):
        return {"requests": self.archive.requests, "response_bytes": self.bytes, "derived_payload_bytes": self.derived_bytes,
                "max_requests": self.archive.max_requests, "max_response_bytes": self.max_bytes,
                "byte_budget_basis": "Retained uncompressed raw responses plus normalized payloads; small manifests excluded; not network bandwidth (an over-budget response may be fetched before rejection)",
                "pages": self.archive.pages, "quality": self.archive.quality}


class _StreamEvidence:
    """Reconstruct transport coverage from hashed event rows, never manifest claims."""
    def __init__(self):
        self.start = self.end = self.gap_start = None
        self.attempts = 0
        self.live = False
        self.failure = None
        self.gaps = []

    @staticmethod
    def boundary(row):
        return (row['receipt_unix_ns'], row['receipt_monotonic_ns'], row['attempt_id'])

    def close_gap(self, row):
        if self.gap_start is not None:
            wall, mono, attempt = self.gap_start
            self.gaps.append({'start_unix_ns': wall, 'end_unix_ns': row['receipt_unix_ns'],
                              'start_monotonic_ns': mono, 'end_monotonic_ns': row['receipt_monotonic_ns'],
                              'start_attempt_id': attempt, 'end_attempt_id': row['attempt_id'],
                              'reason': 'No confirmed stream subscription'})
            self.gap_start = None

    def accept(self, row):
        kind, payload, attempt = row['kind'], row['payload'], row['attempt_id']
        if self.end is not None:
            raise ValueError('Recording contains rows after its terminal event.')
        if self.start is None:
            if kind != 'recorder_start' or attempt != 0:
                raise ValueError('Recording must begin with a recorder_start event.')
            self.start = row
            self.gap_start = self.boundary(row)
            return
        if kind == 'attempt_start':
            if attempt != self.attempts + 1 or self.live:
                raise ValueError('Invalid stream attempt transition.')
            self.attempts = attempt
            self.failure = None
            return
        if attempt != self.attempts:
            raise ValueError('Recording row has an inconsistent attempt ID.')
        if kind == 'transport_status':
            if not attempt or payload.get('state') not in ('connecting', 'live'):
                raise ValueError('Invalid transport status transition.')
            if payload['state'] == 'live':
                if self.live:
                    raise ValueError('Duplicate live transport transition.')
                self.close_gap(row)
                self.live = True
        elif kind in ('transport_error', 'recorder_error'):
            if kind == 'transport_error' and not attempt:
                raise ValueError('Transport error has no connection attempt.')
            self.failure = payload.get('error_type')
        elif kind == 'transport_disconnected':
            if not attempt:
                raise ValueError('Disconnect has no connection attempt.')
            # An initial failed attempt must not replace the still-open initial
            # gap. A live-to-disconnected transition starts at this exact row.
            if self.live:
                self.gap_start = self.boundary(row)
            self.live = False
        elif kind == 'recorder_end':
            self.close_gap(row)
            self.end = row
        elif kind not in _EVENTS or not attempt:
            raise ValueError('Unexpected event in recording transcript.')

    def derived(self):
        if self.start is None or self.end is None:
            raise ValueError('Recording lacks hashed start or terminal evidence.')
        config, terminal = self.start['payload'], self.end['payload']
        elapsed = (self.end['receipt_monotonic_ns'] - self.start['receipt_monotonic_ns']) / 1e9
        reason, dropped = terminal.get('termination'), terminal.get('dropped_records')
        if type(dropped) is not int or dropped < 0 or terminal.get('failure') != self.failure:
            raise ValueError('Recording terminal failure evidence is inconsistent.')
        if self.attempts > config['max_attempts']:
            raise ValueError('Recorded attempts exceed the registered maximum.')
        if reason == 'duration_limit' and elapsed < config['duration_seconds']:
            raise ValueError('Duration-limit termination precedes the declared deadline.')
        if reason == 'attempts_exhausted' and self.attempts != config['max_attempts']:
            raise ValueError('Attempt-exhaustion termination has inconsistent attempts.')
        if reason == 'stream_connection_limit' and self.failure != 'stream_connection_limit':
            raise ValueError('Connection-limit termination lacks its transport error.')
        if reason in ('event_limit', 'byte_limit') and dropped < 1:
            raise ValueError('Budget termination lacks dropped-record evidence.')
        if reason not in ('duration_limit', 'attempts_exhausted', 'stream_connection_limit',
                          'event_limit', 'byte_limit', 'setup_or_recording_failure', 'stream_stopped_early'):
            raise ValueError('Unknown recording termination reason.')
        status = ('complete_bounded_capture' if reason == 'duration_limit' and self.live
                  and self.failure is None and not dropped else 'incomplete')
        return {'attempts': self.attempts, 'status': status, 'gaps': self.gaps,
                'failure': self.failure, 'termination': reason, 'dropped_records': dropped,
                'started_at_ns': self.start['receipt_unix_ns'],
                'started_monotonic_ns': self.start['receipt_monotonic_ns'],
                'ended_at_ns': self.end['receipt_unix_ns'],
                'ended_monotonic_ns': self.end['receipt_monotonic_ns'],
                'elapsed_seconds': elapsed}


def record_session(output, symbols, duration_seconds=180, max_events=200000,
                   max_bytes=128*_MIB, max_attempts=2, stream=None):
    """Bounded callback capture with hashed start, attempt and terminal evidence.

    Byte limits govern retained JSONL, not network bandwidth. One record and
    2048 bytes are reserved for terminal evidence even when a limit is hit.
    """
    symbols = _symbols(symbols)
    if type(duration_seconds) not in (int, float) or not 0 < duration_seconds <= 300:
        raise ValueError('Recording duration must be between zero and 300 seconds.')
    if type(max_events) is not int or max_events < 2 or type(max_bytes) is not int or max_bytes < 4096:
        raise ValueError('Recording requires at least two records and 4096 retained bytes.')
    if type(max_attempts) is not int or not 1 <= max_attempts <= 2:
        raise ValueError('At most two stream connection attempts are supported.')
    directory = _new_directory(output)
    manifest = {'schema_version': 2, 'kind': 'prospective_parsed_events', 'source': 'alpaca', 'feed': 'sip',
                'symbols': symbols, 'status': 'incomplete', 'duration_limit_seconds': duration_seconds,
                'max_events': max_events, 'max_bytes': max_bytes, 'max_attempts': max_attempts,
                'receipt_basis': 'Python callback entry wall and monotonic clocks; not socket receipt',
                'wire_payloads_preserved': False, 'original_provider_fields_preserved': True,
                'historical_universe_established': False, 'halt_status_at_start': 'unknown',
                'clock_sync_accuracy': 'unmeasured', 'channel_statuses': [],
                'required_channels': ['trades', 'quotes', 'bars', 'updatedBars', 'dailyBars'],
                'optional_channels': ['statuses', 'lulds'],
                'automatic_channels': ['corrections', 'cancelErrors'],
                'subscription_ack_basis': 'stream_live validated required ACK; optional callbacks preserved; raw ACK not exposed',
                'byte_budget_basis': 'Retained JSONL only; not network bandwidth; terminal row reserved'}
    stop, deadline_reached = threading.Event(), threading.Event()
    begin = (time.time_ns(), time.monotonic_ns())
    def deadline():
        deadline_reached.set()
        stop.set()
    timer = threading.Timer(duration_seconds, deadline)
    timer.daemon = True
    chain, count, size, dropped, attempt = '0'*64, 0, 0, 0, 0
    kinds, digest, evidence = Counter(), hashlib.sha256(), _StreamEvidence()
    termination = 'duration_limit'
    handle = (directory/'events.jsonl').open('xb')

    def append(kind, payload, receipt=None, terminal=False):
        nonlocal chain, count, size, dropped, termination
        wall, mono = receipt or (time.time_ns(), time.monotonic_ns())
        row = {'seq': count+1, 'attempt_id': attempt, 'kind': kind,
               'receipt_unix_ns': wall, 'receipt_monotonic_ns': mono,
               'provider_event_time_raw': payload.get('t') if isinstance(payload,dict) else None,
               'payload': payload, 'previous_sha256': chain}
        row['sha256'] = _sha(_canonical(row))
        encoded = _canonical(row)+b'\n'
        if not terminal and (count >= max_events-1 or size+len(encoded)+2048 > max_bytes):
            dropped += 1
            termination = 'event_limit' if count >= max_events-1 else 'byte_limit'
            stop.set()
            return False
        if count >= max_events or size+len(encoded) > max_bytes:
            raise ValueError('Reserved terminal recording space was insufficient.')
        handle.write(encoded)
        digest.update(encoded)
        evidence.accept(row)
        chain,count,size=row['sha256'],count+1,size+len(encoded)
        kinds[kind]+=1
        if count%256==0:handle.flush()
        return True

    def event(payload):
        receipt=(time.time_ns(),time.monotonic_ns())
        if not isinstance(payload,dict) or payload.get('T') not in _EVENTS:
            raise ValueError('Unexpected callback event type; recording stopped.')
        if stop.is_set():return
        if append(payload['T'],payload,receipt) and payload['T']=='nomisma_subscription':
            manifest['channel_statuses'].append({'receipt_unix_ns':receipt[0],
                **{key:payload.get(key) for key in ('required','statuses','lulds')}})

    def status(value):
        if value not in ('connecting','live'):raise ValueError('Unexpected transport status.')
        if not stop.is_set():append('transport_status',{'state':value})

    append('recorder_start',{'symbols':symbols,'duration_seconds':duration_seconds,
                           'max_events':max_events,'max_bytes':max_bytes,'max_attempts':max_attempts},begin)
    try:
        if stream is None:
            status_info,unused_headers,unused_account=live_data._credentials()
            if status_info['feed']!='sip':raise ValueError('Prospective research recording requires SIP.')
            stream=live_data.stream_live
        timer.start()
        for next_attempt in range(1,max_attempts+1):
            if stop.is_set():break
            attempt=next_attempt
            if not append('attempt_start',{}):
                attempt=evidence.attempts
                break
            failure=None
            try:
                stream(symbols,event,stop,status)
                if not stop.is_set():failure='unexpected_stream_return'
            except Exception as error:
                failure=_error_code(error)
            if failure is not None:
                append('transport_error',{'error_type':failure})
                append('transport_disconnected',{'error_type':failure})
                if failure=='stream_connection_limit' and termination not in ('event_limit','byte_limit'):
                    termination='stream_connection_limit';stop.set()
            if stop.is_set():break
            if next_attempt<max_attempts:stop.wait(.5)
        if termination=='duration_limit':
            if not stop.is_set():termination='attempts_exhausted'
            elif not deadline_reached.is_set():termination='stream_stopped_early'
    except Exception as error:
        failure=_error_code(error)
        append('recorder_error',{'error_type':failure})
        if termination not in ('event_limit','byte_limit'):termination='setup_or_recording_failure'
    finally:
        stop.set();timer.cancel()
        # Manifest coverage/attempts/status are derived from the same terminal
        # transcript that the offline verifier independently reconstructs.
        attempt=evidence.attempts
        append('recorder_end',{'termination':termination,'failure':evidence.failure,
                               'dropped_records':dropped},terminal=True)
        handle.flush();handle.close()
        manifest.update(evidence.derived())
        manifest.update(counts=dict(kinds),records=count,bytes=size,final_chain_sha256=chain,
                        events_file='events.jsonl',events_sha256=digest.hexdigest())
        _write(directory/'manifest.json',manifest)
    return directory/'manifest.json'


def verify_recording(path):
    """Verify transport coverage, limits and receipt provenance from hashed rows."""
    path=Path(path).resolve();manifest=json.loads(path.read_bytes())
    if manifest.get('schema_version')!=2 or manifest.get('kind')!='prospective_parsed_events':
        raise ValueError('Unsupported prospective recording schema.')
    if manifest.get('events_file')!='events.jsonl':raise ValueError('Invalid recording artifact path.')
    events=path.parent/'events.jsonl'
    if events.is_symlink():raise ValueError('Recording file cannot be a symbolic link.')
    chain,count,size='0'*64,0,0
    kinds,digest,evidence=Counter(),hashlib.sha256(),_StreamEvidence()
    wall_regressions=0;prior_mono=prior_wall=None;channel_statuses=[]
    with events.open('rb') as handle:
        for line in handle:
            digest.update(line);size+=len(line);row=json.loads(line);count+=1
            claimed=row.pop('sha256',None)
            if row.get('seq')!=count or row.get('previous_sha256')!=chain or _sha(_canonical(row))!=claimed:
                raise ValueError('Recording event sequence or hash chain differs.')
            mono,wall=row.get('receipt_monotonic_ns'),row.get('receipt_unix_ns')
            if type(mono) is not int or type(wall) is not int or (prior_mono is not None and mono<prior_mono):
                raise ValueError('Invalid or decreasing monotonic receipt timestamp.')
            if prior_wall is not None and wall<prior_wall:wall_regressions+=1
            evidence.accept(row)
            if row['kind']=='nomisma_subscription':
                channel_statuses.append({'receipt_unix_ns':wall,
                    **{key:row['payload'].get(key) for key in ('required','statuses','lulds')}})
            prior_mono,prior_wall=mono,wall;chain=claimed;kinds[row['kind']]+=1
    derived=evidence.derived()
    if any(manifest.get(key)!=value for key,value in derived.items()):
        raise ValueError('Recording manifest transport/coverage differs from hashed transcript.')
    config=evidence.start['payload']
    for key in ('symbols','max_events','max_bytes','max_attempts'):
        if manifest.get(key)!=config[key]:raise ValueError('Recording limits differ from hashed registration.')
    if manifest.get('duration_limit_seconds')!=config['duration_seconds']:
        raise ValueError('Recording duration limit differs from hashed registration.')
    if (count!=manifest['records'] or size!=manifest['bytes'] or chain!=manifest['final_chain_sha256']
            or digest.hexdigest()!=manifest['events_sha256'] or dict(kinds)!=manifest['counts']
            or manifest['channel_statuses']!=channel_statuses):
        raise ValueError('Recording manifest does not reconcile with event bytes.')
    if count>manifest['max_events'] or size>manifest['max_bytes']:
        raise ValueError('Recording resource budget exceeded.')
    return {'verified':True,'status':derived['status'],'records':count,'bytes':size,
            'counts':dict(kinds),'wall_clock_regressions':wall_regressions,'gaps':derived['gaps'],
            'attempts':derived['attempts'],'elapsed_seconds':derived['elapsed_seconds'],
            'duration_overrun_seconds':max(0,derived['elapsed_seconds']-config['duration_seconds']),
            'receipt_basis':manifest['receipt_basis'],'coverage_complete':False,
            'limitations':'Bounded callback capture; unknown pre-start status and no proof of feed completeness or real execution.'}


def capture_metadata(output, symbols, max_requests=8, requester=None):
    """GET only clock/calendar/assets/actions; no account, position or order API."""
    symbols=_symbols(symbols);directory=_new_directory(output)
    budget=_Budget(directory,max_requests,64*_MIB,requester)
    archive=budget.archive
    now=datetime.now(_NY).date()
    manifest={'schema_version':1,'kind':'current_research_metadata','symbols':symbols,'status':'incomplete',
              'universe_basis':'Current asset snapshot available from retrieval only; cannot be backdated.',
              'corporate_action_availability':'Provider does not guarantee announcement-time availability.',
              'items':{},'unavailable':[]}
    try:
        for label,url,params in (
            ('clock_start',budget.account_url+'/v2/clock',{}),
            ('calendar',budget.account_url+'/v2/calendar',{'start':(now-timedelta(days=100)).isoformat(),'end':(now+timedelta(days=45)).isoformat()}),
            ('current_assets',budget.account_url+'/v2/assets',{'asset_class':'us_equity'})):
            payload=archive.request(url,params)
            manifest['items'][label]={'page_path':archive.pages[-1]['path'],'received_at':archive.pages[-1]['retrieved_at'],
                                       'records':len(payload) if isinstance(payload,list) else None}
        params={'symbols':','.join(symbols),'start':(now-timedelta(days=180)).isoformat(),
                'end':(now+timedelta(days=30)).isoformat(),'data_quality':'all','limit':1000,'sort':'asc'}
        seen=set();action_pages=[]
        try:
            while True:
                if archive.requests>=max_requests-1:
                    raise ValueError('Corporate action metadata request budget exhausted.')
                payload=archive.request('https://data.alpaca.markets/v1/corporate-actions',params)
                action_pages.append(archive.pages[-1]['path'])
                if not isinstance(payload,dict):raise ValueError('Malformed corporate action metadata.')
                token=payload.get('next_page_token')
                if not token:break
                if not isinstance(token,str) or token in seen:raise ValueError('Invalid corporate action pagination.')
                seen.add(token);params['page_token']=token
            manifest['items']['corporate_actions']={'page_paths':action_pages,'complete_pagination':True}
        except ValueError as error:
            manifest['unavailable'].append({'item':'corporate_actions','reason':_error_code(error),'page_paths':action_pages})
        archive.request(budget.account_url+'/v2/clock',{})
        manifest['items']['clock_end']={'page_path':archive.pages[-1]['path'],'received_at':archive.pages[-1]['retrieved_at']}
        manifest['status']='complete_with_unavailable_metadata' if manifest['unavailable'] else 'complete'
    except Exception as error:
        manifest['failure']=_error_code(error)
        raise
    finally:
        manifest.update(budget.summary());_write(directory/'manifest.json',manifest)
    return directory/'manifest.json'


def acquire_preflight(output, symbols, session_count=20, end_date='2026-09-02',
                      max_requests=100, max_bytes=256*_MIB, requester=None):
    """Registered minute-only development coverage study, never a fill dataset."""
    symbols=_symbols(symbols)
    if type(session_count) is not int or not 1<=session_count<=20:
        raise ValueError('Preflight supports 1 to 20 explicitly bounded sessions.')
    end=providers._date(end_date)
    if end>=datetime.now(_NY).date():raise ValueError('Preflight requires prior completed session dates.')
    directory=_new_directory(output);budget=_Budget(directory,max_requests,max_bytes,requester);archive=budget.archive
    manifest={'schema_version':1,'kind':'minute_only_preflight','status':'incomplete','symbols':symbols,
              'historical_universe_established':False,'partition':'retrospective_development',
              'not_execution_dataset':True,'missing_bar_policy':'Unknown missing/no eligible trades; no invented OHLCV or fills.',
              'sessions':[],'registration_path':'registration.json'}
    try:
        calendar=archive.request(budget.account_url+'/v2/calendar',{'start':(end-timedelta(days=200)).isoformat(),'end':end.isoformat()})
        if not isinstance(calendar,list):raise ValueError('Malformed exchange calendar.')
        days=sorted({providers._date(row['date']).isoformat() for row in calendar if isinstance(row,dict) and row.get('date')<=end.isoformat()})[-session_count:]
        if len(days)!=session_count:raise ValueError('Calendar lacks requested development session count.')
        registration={'schema_version':1,'frozen_before_bar_requests':True,'frozen_at':datetime.now(timezone.utc).isoformat(),
                      'symbols':symbols,'session_dates':days,'requested_end_date':end.isoformat(),'session_count':session_count,
                      'calendar_body_sha256':archive.pages[-1]['body_sha256'],'max_requests':max_requests,'max_response_bytes':max_bytes,
                      'partition':'retrospective_development','tick_acquisition_rule':'No tick acquisition or outcome-based selection in preflight.'}
        _write(directory/'registration.json',registration)
        manifest['registration_sha256']=_sha(_canonical(registration))
        (directory/'sessions').mkdir()
        all_symbols=sorted(set(symbols)|{'SPY'})
        for day in days:
            session,unused=live_data._session(calendar,datetime.combine(date.fromisoformat(day),daytime(23),_NY))
            if session['date']!=day or len(session['prior_dates'])!=30:raise ValueError('Incomplete prior-session calendar baseline.')
            start=datetime.combine(date.fromisoformat(day),daytime(4),_NY).isoformat()
            finish=datetime.combine(date.fromisoformat(day),daytime(20),_NY).isoformat()
            daily_start=datetime.combine(date.fromisoformat(day)-timedelta(days=100),daytime.min,_NY).isoformat()
            daily_end=datetime.combine(date.fromisoformat(day),daytime.min,_NY).isoformat()
            params={'start':start,'end':finish,'feed':'sip','asof':day,'timeframe':'1Min'}
            raw=archive.paged('bars',all_symbols,dict(params,adjustment='raw'))
            split=archive.paged('bars',all_symbols,dict(params,adjustment='split'))
            daily=archive.paged('bars',all_symbols,{'start':daily_start,'end':daily_end,'feed':'sip','asof':day,'timeframe':'1Day','adjustment':'split'})
            opened,closed=replay_data.timestamp_ns(session['open']),replay_data.timestamp_ns(session['close'])
            expected=list(range(opened,closed,60*10**9));assets=[];stats=[]
            for symbol in all_symbols:
                context={'symbol':symbol,'session_date':day}
                minutes=replay_data._bars(raw[symbol],replay_data.timestamp_ns(start),replay_data.timestamp_ns(finish),archive.quality,dict(context,adjustment='raw'))
                adjusted=replay_data._bars(split[symbol],replay_data.timestamp_ns(start),replay_data.timestamp_ns(finish),archive.quality,dict(context,adjustment='split'))
                prior=replay_data._bars(daily[symbol],replay_data.timestamp_ns(daily_start),replay_data.timestamp_ns(daily_end),archive.quality,dict(context,adjustment='split_daily'),daily=True)
                factor,error=replay_data._basis(minutes,adjusted,opened)
                rebased=replay_data._rescale_daily(prior,factor) if factor is not None else []
                actual={replay_data.timestamp_ns(bar['t']) for bar in minutes if opened<=replay_data.timestamp_ns(bar['t'])<closed}
                missing=[stamp for stamp in expected if stamp not in actual]
                prefix=0
                for stamp in expected:
                    if stamp not in actual:break
                    prefix+=1
                consecutive=windows=0
                for stamp in expected:
                    consecutive=consecutive+1 if stamp in actual else 0
                    windows+=consecutive>=21
                missing_prior=sorted(set(session['prior_dates'])-{bar['date'] for bar in rebased})
                summary={'symbol':symbol,'role':'benchmark' if symbol=='SPY' and symbol not in symbols else 'cohort',
                         'minute_bars':len(minutes),'rth_bars':len(actual),'expected_rth_slots':len(expected),
                         'missing_rth_slots':len(missing),'from_open_contiguous_minutes':prefix,
                         'from_open_decisions_with_21_bars':max(0,prefix-20),'rolling_21_minute_windows':windows,
                         'missing_prior_dates':missing_prior,'split_factor':str(factor) if factor is not None else None,
                         'data_blockers':([error] if error else [])+(['Missing prior baseline sessions.'] if missing_prior else [])}
                stats.append(summary)
                assets.append({'symbol':symbol,'minutes':minutes,'daily':rebased,'quality':summary,
                               'missing_rth_timestamps_ns':missing})
            payload={'kind':'minute_only_preflight_session','session':session,'assets':assets}
            relative='sessions/'+day+'.json';content=_canonical(payload);budget.reserve_derived(len(content));(directory/relative).write_bytes(content)
            manifest['sessions'].append({'date':day,'path':relative,'sha256':_sha(content),'stats':stats})
            del payload,assets,raw,split,daily,content
        manifest['status']='complete'
    except Exception as error:
        manifest['failure']=_error_code(error)
        raise
    finally:
        manifest.update(budget.summary());_write(directory/'manifest.json',manifest)
    return directory/'manifest.json'
