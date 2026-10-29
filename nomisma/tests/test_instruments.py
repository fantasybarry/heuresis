"""Offline stock classification and live-entry enforcement regressions."""
import io
import threading
import unittest
from unittest.mock import patch
from nomisma import instruments, research, live_data, providers


class InstrumentTests(unittest.TestCase):
    def setUp(self):
        self.old = instruments._CACHE
        instruments._CACHE = None
        self.addCleanup(setattr, instruments, '_CACHE', self.old)

    def test_only_company_stock_and_depositary_shares(self):
        names = [('A', 'Acme Common Stock', 'N'), ('B', 'Company Ordinary Shares', 'N'),
                 ('C', 'Company American Depositary Shares', 'N'),
                 ('SPY', 'SPDR Common Shares', 'Y'), ('FUND', 'Growth Fund Common Stock', 'N'),
                 ('W', 'Company Common Stock Warrants', 'N'), ('U', 'Company Units', 'N'),
                 ('P', 'Company Preferred Stock', 'N'), ('R', 'Company Rights', 'N'),
                 ('ETN', 'Bank Notes', 'N'), ('UNKNOWN', 'Unknown', 'N')]
        body = 'Symbol|Security Name|ETF|Test Issue\n' + '\n'.join(
            f'{symbol}|{name}|{etf}|N' for symbol, name, etf in names)
        self.assertEqual(instruments._parse(body, True), {'A', 'B', 'C'})

    def test_share_class_aliases_and_test_issues(self):
        body = ('ACT Symbol|Security Name|CQS Symbol|NASDAQ Symbol|ETF|Test Issue\n'
                'BRK.B|Berkshire Common Stock|BRK.B|BRK.B|N|N\n'
                'TEST|Test Common Stock|TEST|TEST|N|Y\n')
        self.assertEqual(instruments._parse(body, False), {'BRK.B'})

    def test_transport_cache_no_credentials_and_fail_closed(self):
        nasdaq = b'Symbol|Security Name|ETF|Test Issue\nA|Acme Common Stock|N|N\n'
        other = b'ACT Symbol|Security Name|ETF|Test Issue\nB|Beta Common Stock|N|N\n'
        with patch.object(instruments, 'urlopen', side_effect=[io.BytesIO(nasdaq), io.BytesIO(other)]) as get:
            self.assertEqual(instruments.stock_symbols(), {'A', 'B'})
            self.assertEqual(instruments.stock_symbols(), {'A', 'B'})
            self.assertEqual(get.call_count, 2)
            self.assertEqual(set(dict(get.call_args.args[0].header_items())), {'User-agent'})
        instruments._CACHE = (-1e10, frozenset({'OLD'}))
        with patch.object(instruments, 'urlopen', side_effect=OSError('private transport text')):
            with self.assertRaisesRegex(providers.ProviderError, 'classification is unavailable'):
                instruments.stock_symbols()

    def test_custom_discovery_cannot_bypass_stocks_only(self):
        with patch.object(instruments, 'stock_symbols', return_value={'AAPL'}):
            rows, _, _, _ = research._universe({'universe':'custom','symbols':['SPY','AAPL']}, {}, '', None, None)
            self.assertEqual(rows, ['AAPL'])
            with self.assertRaisesRegex(ValueError, 'No verified'):
                research._universe({'universe':'custom','symbols':['SPY']}, {}, '', None, None)

    def test_manual_live_selection_rejects_non_stocks_before_history(self):
        with patch.object(instruments, 'stock_symbols', return_value={'AAPL'}), \
             patch.object(live_data, '_credentials', return_value=({'feed':'sip'}, {}, 'https://paper-api.alpaca.markets')), \
             patch.object(live_data, '_get_json') as get:
            with self.assertRaisesRegex(providers.ProviderError, 'SPY'):
                live_data.load_live_seed(['SPY'])
            get.assert_not_called()
