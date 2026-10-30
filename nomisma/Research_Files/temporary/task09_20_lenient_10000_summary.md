# Lenient entry simulation — $10,000 cash

Reran six stocks and six exit rules with **$10,000 starting cash per alternative account**, wider entry-price allowances, and minimum reward/risk reduced from **1.5 to 1.0**.

| Stock | Trades per rule | Net result across six exits |
|---|---:|---:|
| FTFT | 2 | −$15.65 to +$184.60 |
| SES | 1 | −$37.16 to −$28.54 |
| TE | 4 | −$274.55 to −$187.17 |
| GRAB | 2 | −$147.34 to −$86.09 |
| RR | 0 | $0 |
| SERV | 2 | −$22.20 to −$9.70 |

Results include modeled costs. Each stock/rule combination is a separate account, not part of one combined portfolio.

Leniency produced **10 additional entry opportunities, but all 10 lost money under every tested exit rule**. More participation did not produce better profitability on the tested dates.

All **98 tests** and **152 audit checks** passed. These checks validate the offline simulation; they do not establish stable profitability.

The full six-rule matrix, share quantities, cash usage and specialist reviews are in [task09_20_lenient_10000.md](task09_20_lenient_10000.md).
