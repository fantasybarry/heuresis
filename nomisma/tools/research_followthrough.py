#!/usr/bin/env python3
"""Bounded research commands. Does not start a monitor or submit orders."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nomisma import calibration, research_data, research_validation
from nomisma.replay_data import digest, file_sha256, write_new


def verified_legacy_candidate(directory, candidate):
    """Read immutable prior checkpoints; never infer policy identity from a folder."""
    directory = Path(directory)/candidate['id']
    manifest = json.loads((directory/'manifest.json').read_text())
    for name, key in [('result.json', 'result_sha256'), ('config.json', 'config_file_sha256'),
                      ('metrics.json', 'metrics_sha256')]:
        if file_sha256(directory/name) != manifest.get(key):
            raise ValueError('Prior checkpoint bytes differ: '+candidate['id']+'/'+name)
    result = json.loads((directory/'result.json').read_text())
    config = json.loads((directory/'config.json').read_text())
    if (config != candidate['config'] or result.get('config') != config or
            manifest.get('identity', {}).get('policy_id') != candidate['id'] or
            result.get('run_fingerprint') != manifest.get('result_run_fingerprint')):
        raise ValueError('Prior checkpoint policy/configuration identity differs.')
    config_digest = digest(config)
    if manifest.get('config_sha256') != config_digest or manifest['identity'].get('config_sha256') != config_digest:
        raise ValueError('Prior checkpoint canonical configuration differs.')
    return result, {'id': candidate['id'], 'result_sha256': manifest['result_sha256'],
                    'checkpoint_manifest_sha256': file_sha256(directory/'manifest.json'),
                    'identity': manifest['identity']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('metadata', 'preflight', 'record'):
        child = sub.add_parser(name)
        child.add_argument('--output', required=True)
        child.add_argument('--registration', required=True)
    child = sub.add_parser('audit')
    child.add_argument('--result', required=True)
    child.add_argument('--output', required=True)
    child = sub.add_parser('inference')
    child.add_argument('--results-root', required=True)
    child.add_argument('--registration', required=True)
    child.add_argument('--output', required=True)
    child = sub.add_parser('risk-run')
    child.add_argument('--catalog', required=True)
    child.add_argument('--config', required=True)
    child.add_argument('--output', required=True)
    child.add_argument('--passive', action='store_true')
    args = parser.parse_args()
    start = time.monotonic()
    if args.command in ('metadata', 'preflight', 'record'):
        from run import load_environment
        load_environment(Path(__file__).resolve().parents[1]/'.env')
        reg = json.loads(Path(args.registration).read_text())
        if reg.get('trading_execution_authorized') is not False or reg.get('research_only') is not True:
            raise ValueError('Research-only registration is required.')
        source_paths = [Path(__file__), Path(research_data.__file__),
                        Path(research_data.live_data.__file__), Path(research_data.replay_data.__file__),
                        Path(research_data.providers.__file__)]
        sources_before = {str(path): file_sha256(path) for path in source_paths}
        execution_start = datetime.now(timezone.utc).isoformat()
        stage = reg['data_stage']
        if args.command == 'metadata':
            manifest = research_data.capture_metadata(args.output, reg['symbols'], max_requests=stage['metadata']['max_requests'])
        elif args.command == 'preflight':
            params = stage['preflight']
            manifest = research_data.acquire_preflight(args.output, reg['symbols'],
                session_count=params['session_count'], end_date=params['end_date'],
                max_requests=params['max_requests'], max_bytes=params['max_retained_payload_bytes'])
        else:
            params = stage['prospective']
            manifest = research_data.record_session(args.output, reg['symbols'],
                duration_seconds=params['duration_seconds'], max_events=params['max_events'],
                max_bytes=params['max_retained_bytes'], max_attempts=params['max_attempts'])
            write_new(Path(args.output)/'verification.json', research_data.verify_recording(manifest))
        sources_after = {str(path): file_sha256(path) for path in source_paths}
        write_new(Path(args.output)/'execution-identity.json', {
            'command': args.command, 'started_at': execution_start,
            'ended_at': datetime.now(timezone.utc).isoformat(),
            'registration_sha256': file_sha256(args.registration),
            'sources_before': sources_before, 'sources_after': sources_after,
            'sources_unchanged': sources_before == sources_after,
            'manifest_sha256': file_sha256(manifest)})
        if sources_before != sources_after:
            raise ValueError('Acquisition source files changed during execution; evidence needs review.')
        print(json.dumps({'manifest': str(manifest), 'elapsed_seconds': time.monotonic()-start}))
    elif args.command == 'audit':
        result = json.loads(Path(args.result).read_text())
        report = research_validation.audit_replay(result)
        report['source_result_sha256'] = file_sha256(args.result)
        write_new(args.output, report)
        print(json.dumps(report['total']))
    elif args.command == 'inference':
        reg = json.loads(Path(args.registration).read_text())
        folds = [{'id': row['id'], 'validation_dates': row['validation']} for row in reg['folds']]
        dates = {day for fold in folds for day in fold['validation_dates']}
        panel, provenance = {}, []
        base = json.loads(Path(args.results_root).joinpath('k1.5-r2-h15/config.json').read_text())
        for candidate in calibration.generate_candidates(base):
            result, identity = verified_legacy_candidate(args.results_root, candidate)
            if provenance and identity['identity']['experiment'] != provenance[0]['identity']['experiment']:
                raise ValueError('Candidate checkpoints belong to different experiments.')
            if result.get('streaming', {}).get('session_dates') != reg['existing_development_dates']:
                raise ValueError('Prior checkpoint dates differ from the registered development panel.')
            provenance.append(identity)
            panel[candidate['id']] = [row for row in calibration.session_metrics(result)['sessions'] if row['date'] in dates]
        report = research_validation.simultaneous_session_bounds(panel, folds, reg['inference'])
        report.update(initial_capital=base['account']['initial_cash'],
            analysis_scope='Reused legacy development checkpoints; separate from the new $1,000 guarded experiment.',
            source_results=provenance,
            registration_sha256=file_sha256(args.registration),
            inference_source_sha256=file_sha256(research_validation.__file__))
        write_new(args.output, report)
        print(json.dumps({'status': report['status'], 'policies': len(panel), 'blockers': report['sampling_screen_failures']}))
    else:
        from nomisma import research_risk
        destination = Path(args.output)
        if destination.exists() and any(destination.iterdir()):
            raise ValueError('Risk run output must be new or empty.')
        config = json.loads(Path(args.config).read_text())
        result = research_risk.run_catalog_guarded(Path(args.catalog), config, guard_enabled=not args.passive)
        write_new(destination/'result.json', result)
        write_new(destination/'metrics.json', calibration.session_metrics(result))
        write_new(destination/'audit.json', research_validation.audit_replay(result))
        write_new(destination/'execution.json', {'elapsed_seconds': time.monotonic()-start,
            'max_rss_native': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'max_rss_unit': 'bytes on macOS; KiB on Linux',
            'result_sha256': file_sha256(destination/'result.json'),
            'config_sha256': file_sha256(args.config),
            'risk_source_sha256': file_sha256(research_risk.__file__)})
        print(json.dumps({'summary': result['summary'], 'output': str(destination), 'elapsed_seconds': time.monotonic()-start}))


if __name__ == '__main__':
    main()
