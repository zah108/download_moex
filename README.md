# MOEX Data Downloader

A script for downloading historical daily data from the Moscow Exchange (MOEX ISS) and building continuous futures price series. Automatically downloads data for 2021–2026, splices sequential contracts into unified time series, and saves results in TSV format.

## 📊 What the Script Does

The script downloads daily data.

### Block 1: Quarterly Futures

Downloads and splices quarterly futures into a continuous price series:

| Ticker | Asset | Description |
| -------- | ------- | ------------- |
| **Si** | USD/RUB | US Dollar to Russian Ruble |
| **CR** | CNY/RUB | Chinese Yuan to Russian Ruble |
| **Ri** | RTS Index | RTS Index |
| **GD** | Gold | Gold (USD per troy ounce) |
| **SV** | Silver | Silver (USD per troy ounce) |
| **PT** | Platinum | Platinum (USD per troy ounce) |
| **SR** | SBER | Sberbank Stock Futures |

**Splicing method:** calendar splicing by expiration date. Each contract is traded until its expiration date (3rd Thursday of the delivery month), after which the series continues with the next contract.

**Quarterly expiration months:**

- **H** — March (month 3)
- **M** — June (month 6)
- **U** — September (month 9)
- **Z** — December (month 12)

**Ticker example:** `SiH4` = dollar futures, expiring in March 2024.

### Block 2: Monthly Commodity Futures

Downloads and splices monthly commodity futures:

| Ticker | Asset | Description |
|--------|-------|-------------|
| **NG** | Natural Gas | Natural gas (RUB per 1000 cubic meters) |
| **BR** | Brent Crude | Brent crude oil (USD per barrel) |

**Splicing method:** dynamic splicing based on actual trading data. Each contract is used until its last available trading date, after which the series continues with the next contract.

**Monthly month codes:**

- **F** — January, **G** — February, **H** — March, **J** — April
- **K** — May, **M** — June, **N** — July, **Q** — August
- **U** — September, **V** — October, **X** — November, **Z** — December

**Ticker example:** `NGF4` = gas futures, expiring in January 2024.

### Block 3: Stocks and Indices

Downloads daily closing prices for 5 years (2021–2026):

**Stocks:**

- **SBER** — Sberbank
- **LKOH** — Lukoil
- **OZON** — Ozon
- **T** — T-Technologies
- **MTSS** — MTS
- **MOEX** — Moscow Exchange
- **NLMK** — NLMK
- **PLZL** — Polyus Gold
- **GOLD** — GOLD Fund
- **AMNY** — AMNY Fund (Yuan)

**Indices:**

- **IMOEX** — MOEX Russia Index

**Data source:** daily candles (24-hour interval) via MOEX ISS API.

## ▶️ Running the Script

```bash
python download_moex-1d.py
```

When running, the script:

1. Creates `txt/` and `logs/` folders (if they don't exist)
2. Downloads data from MOEX ISS
3. Splices futures into continuous series
4. Saves results to TSV files
5. Maintains execution logs in `logs/YYYY-MM-download.log`

**Execution time:** ~3-5 minutes (depends on internet speed and MOEX load)

## 📁 Output File Structure

### Futures (Continuous Series)

**Quarterly futures:**

- `Si-all-d.txt` — USD/RUB
- `CR-all-d.txt` — CNY/RUB
- `Ri-all-d.txt` — RTS Index
- `GD-all-d.txt` — Gold
- `SV-all-d.txt` — Silver
- `PT-all-d.txt` — Platinum
- `SR-all-d.txt` — Sberbank futures

**Monthly futures:**

- `NG-all-d.txt` — Natural gas
- `BR-all-d.txt` — Brent crude oil

### Stocks and Indices

- `SBER-d-5y.txt` — Sberbank
- `LKOH-d-5y.txt` — Lukoil
- `IMOEX-d-5y.txt` — MOEX Russia Index
- `OZON-d-5y.txt` — Ozon
- `T-d-5y.txt` — T-Technologies
- `MTSS-d-5y.txt` — MTS
- `MOEX-d-5y.txt` — Moscow Exchange
- `NLMK-d-5y.txt` — NLMK
- `PLZL-d-5y.txt` — Polyus Gold
- `GOLD-d-5y.txt` — GOLD Fund
- `AMNY-d-5y.txt` — AMNY Fund (Yuan)

## 📊 Data Format

All files are in **TSV** (Tab-Separated Values) format:

### File Structure

```
Date Close Ticker
2021-01-04 73.4500 Si
2021-01-05 73.1200 Si
2021-01-06 72.8900 Si
...
```

### Columns

| Column | Type | Description |
| -------- | ------ | ------------- |
| **Date** | `YYYY-MM-DD` | Trading date (file index) |
| **Close** | `float` | Closing price |
| **Ticker** | `string` | Contract ticker code (for futures) or underlying asset (for stocks) |

### Features

- **Delimiter:** tab (`\t`)
- **Encoding:** UTF-8
- **Index:** date in the first column
- **Duplicates:** removed (by date)
- **Sorting:** by date (ascending)
- **Range:** 2021-01-01 — 2026-12-31

## 📝 Logs

The script maintains detailed logs in the `logs/` folder:

**File name:** `YYYY-MM-download.log` (e.g., `2026-01-download.log`)

**Content:**

```
[2026-01-15 14:23:45] 🚀 Starting MOEX download
🔄 Starting continuous download and calendar splicing of Si futures...
📊 Si splicing completed. File created: txt/Si-all-d.txt
🔄 Starting continuous download and calendar splicing of CR futures...
...
[2026-01-15 14:28:12] ✅ Download completed
```

**Message levels:**

- `🚀` — start/completion
- `🔄` — process start
- `📊` — successful completion
- `📈` — stock download
- `⚠️` — warnings (ticker skip, HTTP errors)
- `❌` — critical errors (network, parsing)
- `✅` — block completion

## ⚙️ Configuration

All settings are in the `CONFIG` dictionary at the beginning of the script:

```python
CONFIG = {
    # Years to download (inclusive)
    "target_years": list(range(2021, 2027)),  # [2021, 2022, 2023, 2024, 2025, 2026]
    
    # Quarterly futures (7 tickers)
    "quarterly_assets": ['Si', 'CR', 'Ri', 'GD', 'SV', 'PT', 'SR'],
    "quarterly_months_map": {'H': 3, 'M': 6, 'U': 9, 'Z': 12},
    
    # Monthly futures (2 tickers)
    "commodity_assets": ['NG', 'BR'],
    "commodity_codes": ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z'],
    
    # Stocks and indices (11 tickers)
    "equity_tickers": ['SBER', 'IMOEX', 'GOLD', 'AMNY', 'LKOH', 'OZON', 'T', 'MTSS', 'MOEX', 'NLMK', 'PLZL'],
    
    # Folder paths
    "output_folder": "txt",   # Folder for TSV files
    "logs_folder": "logs"     # Folder for logs
}
```

### Modifying Configuration

**Add a new futures contract:**

```python
"quarterly_assets": ['Si', 'CR', 'Ri', 'GD', 'SV', 'PT', 'SR', 'ED'],  # ED — EUR/USD
```

**Change the year range:**

```python
"target_years": list(range(2020, 2027)),  # Starting from 2020
```

**Change the output folder:**

```python
"output_folder": "data/moex"  # Instead of "txt"
```

## 📝 Requirements

- **Python:** 3.8+
- **requests:** >= 2.28.0
- **pandas:** >= 1.5.0
- **urllib3:** >= 1.26.0

## ⚠️ Notes

- **SSL verification:** The script disables SSL certificate verification to work around MOEX certificate issues. In production environments, it's recommended to configure proper CA certificates.
- **Data source:** Public MOEX ISS API (<https://moex.com/iss/>)
- **Rate limiting:** The script doesn't use artificial delays — MOEX doesn't ban for fast requests
- **Warranty:** Data is provided "as is". Always verify data correctness before using in trading systems.

## 📄 License

MIT License — free use with attribution.

## 📞 Contact

If you have questions or suggestions, create an issue in the repository.

## 🙏 Acknowledgments

- **Moscow Exchange (MOEX)** — for providing the open ISS API
- **Python Community** — for excellent libraries (requests, pandas)
