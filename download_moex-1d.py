import os
import ssl
import sys
import requests
import urllib3
import pandas as pd
from datetime import datetime, timedelta
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# =====================================================================
# РАЗДЕЛ CONFIG: НАСТРОЙКИ СКАЧИВАНИЯ И ПАРАМЕТРЫ ТИКЕРОВ
# =====================================================================
CONFIG = {
    # Конфигурация годов исследования по ТЗ
    "target_years": list(range(2021, 2027)),
    
    # Параметры квартальных фьючерсов
    "quarterly_assets": ['Si', 'CR', 'Ri', 'GD', 'SV', 'PT', 'SR'],
    "quarterly_months_map": {'H': 3, 'M': 6, 'U': 9, 'Z': 12},
    
    # Параметры ежемесячных товарных фьючерсов
    "commodity_assets": ['NG', 'BR'],
    "commodity_codes": ['F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z'],
    
    # Дневные тикеры акций и индексов за 5 лет
    "equity_tickers": ['SBER', 'IMOEX', 'GOLD', 'AMNY', 'LKOH', 'OZON', 'T', 'MTSS', 'MOEX', 'NLMK', 'PLZL'],
    
    # Пути к рабочим директориям
    "output_folder": "txt",
    "logs_folder": "logs",
    
    # Сетевые настройки
    "request_timeout": 15,
    "max_retries": 3,               # Максимальное число повторов при сбое
    "max_pages": 500,               # Лимит страниц для защиты от зацикливания
    "page_size_threshold": 100,     # Порог размера страницы для завершения пагинации
}

# =====================================================================
# НАСТРОЙКА БЕЗОПАСНОГО ОКРУЖЕНИЯ ДЛЯ РАБОТЫ С MOEX ISS
# =====================================================================
# ВНИМАНИЕ: Отключение верификации SSL — используется только для обхода
# проблем с сертификатами MOEX. В production-среде рекомендуется настроить
# корректные CA-сертификаты вместо отключения проверки.
ssl._create_default_https_context = ssl._create_unverified_context
os.environ.update({'CURL_CA_BUNDLE': '', 'PYTHONHTTPSVERIFY': '0'})
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
sys.dont_write_bytecode = True

output_folder = CONFIG["output_folder"]
logs_folder = CONFIG["logs_folder"]

for folder in [output_folder, logs_folder]:
    if not os.path.exists(folder):
        os.makedirs(folder)

target_years = CONFIG["target_years"]

# =====================================================================
# НАСТРОЙКА ПОМЕСЯЧНОГО ЛОГИРОВАНИЯ (БЕЗ УДАЛЕНИЯ СТАРЫХ ЛОГОВ)
# =====================================================================
log_file_path = os.path.join(logs_folder, f"{datetime.now().strftime('%Y-%m')}-download.log")


def log_message(message):
    """Выводит сообщение в консоль и дублирует его в лог (без timestamp)."""
    print(message)
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")


def log_blank():
    """Выводит пустую строку в консоль и дублирует в лог."""
    print()
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write("\n")


def log_console_with_timestamp(message):
    """Выводит сообщение с timestamp в консоль и дублирует в лог."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(line)
    with open(log_file_path, "a", encoding="utf-8") as log_file:
        log_file.write(line + "\n")


# =====================================================================
# СОЗДАНИЕ HTTP-СЕССИИ С RETRY-МЕХАНИЗМОМ
# =====================================================================
def create_moex_session():
    """
    Создаёт HTTP-сессию с настроенным retry-механизмом.
    
    Retry-стратегия:
    - Повторяет запросы при статус-кодах 429, 500, 502, 503, 504
    - Exponential backoff: 1с, 2с, 4с между попытками
    - Повторяет при ошибках соединения (ConnectionError, ReadTimeout)
    
    Returns:
        requests.Session: Готовая к использованию сессия.
    """
    session = requests.Session()
    session.trust_env = False
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    
    retry_strategy = Retry(
        total=CONFIG["max_retries"],
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session


# =====================================================================
# СТАРТОВОЕ СООБЩЕНИЕ
# =====================================================================
log_blank()
log_console_with_timestamp("🚀 Запуск загрузки с МОЕХ (download)")


# =====================================================================
# МАТЕМАТИЧЕСКИЙ РАСЧЕТ ДАТЫ ЭКСПИРАЦИИ ДЛЯ КВАРТАЛЬНЫХ КОНТРАКТОВ
# =====================================================================
# Дата экспирации квартального фьючерса MOEX — третий четверг
# месяца экспирации. Это стандартное правило биржи.
def get_quarterly_expiry_date(year, month_num):
    """
    Вычисляет дату экспирации квартального фьючерса (3-й четверг месяца).
    
    Args:
        year: Год экспирации.
        month_num: Номер месяца экспирации (3, 6, 9, 12).
    
    Returns:
        datetime.date: Дата экспирации (третий четверг месяца).
    """
    first_day = datetime(year, month_num, 1)
    thursdays = []
    for i in range(31):
        current_day = first_day + timedelta(days=i)
        if current_day.month != month_num:
            break
        if current_day.weekday() == 3:  # 3 — четверг в Python
            thursdays.append(current_day)
    return thursdays[2].date()


# =====================================================================
# НАДЕЖНЫЙ ПОТОКОВЫЙ ЗАГРУЗЧИК ИЗ ВЕЧНОГО АРХИВА ИТОГОВ ТОРГОВ MOEX ISS
# =====================================================================
def fetch_moex_history(ticker, session=None):
    """
    Загружает историю торгов фьючерса из архива MOEX ISS.
    
    Использует пагинацию через параметр 'start'. Защита от зацикливания
    реализована через лимит максимального числа страниц (max_pages).
    
    Args:
        ticker: Код тикера фьючерса (например, 'SiH4').
        session: HTTP-сессия для переиспользования соединения.
                 Если None, создаётся новая сессия.
    
    Returns:
        pd.DataFrame: DataFrame с колонками [Close, Ticker], 
                      индекс — дата (datetime.date).
                      Пустой DataFrame при ошибке или отсутствии данных.
    """
    domain = "https://moex.com"
    url = f"{domain}/iss/history/engines/futures/markets/forts/securities/{ticker}.json"
    
    all_data = []
    start_pointer = 0
    page_count = 0
    own_session = session is None
    
    if own_session:
        session = create_moex_session()
    
    try:
        while page_count < CONFIG["max_pages"]:
            params = {'from': '2021-01-01', 'start': start_pointer}
            response = session.get(url, params=params, verify=False, 
                                   timeout=CONFIG["request_timeout"])
            
            if response.status_code != 200:
                log_message(f"⚠️ HTTP {response.status_code} для {ticker}")
                break
            
            res = response.json()
            
            if 'history' not in res or not res['history']['data']: 
                break
                
            columns = res['history']['columns']
            date_idx = columns.index('TRADEDATE')
            close_idx = columns.index('CLOSE')
            
            page_data = res['history']['data']
            for row in page_data:
                if row[close_idx] is not None:
                    all_data.append([row[date_idx], row[close_idx]])
                    
            start_pointer += len(page_data)
            page_count += 1
            
            if len(page_data) < CONFIG["page_size_threshold"]:
                break
            
    except requests.exceptions.RequestException as e:
        log_message(f"❌ Сетевая ошибка при загрузке {ticker}: {e}")
        return pd.DataFrame()
    except (KeyError, ValueError, TypeError) as e:
        log_message(f"❌ Ошибка парсинга данных для {ticker}: {e}")
        return pd.DataFrame()
    except Exception as e:
        log_message(f"❌ Непредвиденная ошибка для {ticker}: {type(e).__name__}: {e}")
        return pd.DataFrame()
    finally:
        if own_session:
            session.close()
        
    if page_count >= CONFIG["max_pages"]:
        log_message(f"⚠️ Достигнут лимит страниц ({CONFIG['max_pages']}) для {ticker}")
        
    if not all_data:
        return pd.DataFrame()
        
    df = pd.DataFrame(all_data, columns=['Date', 'Close'])
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    df['Ticker'] = ticker
    return df.drop_duplicates(subset=['Date']).set_index('Date').sort_index()


# =====================================================================
# БЛОК 1: СКЛЕЙКА КВАРТАЛЬНЫХ ФЬЮЧЕРСОВ (Si, CR, Ri, GD, SV, PT, SR)
# =====================================================================
# Календарная склейка — метод построения непрерывного ценового ряда
# из последовательных фьючерсных контрактов. Каждый контракт торгуется
# до даты своей экспирации, после чего ряд продолжается следующим контрактом.
quarterly_assets = CONFIG["quarterly_assets"]
quarterly_months_map = CONFIG["quarterly_months_map"]

# Создаём одну сессию на весь блок для переиспользования соединения
moex_session = create_moex_session()

for asset in quarterly_assets:
    log_message(f"🔄 Запуск сплошного скачивания и календарной склейки фьючерса {asset}...")
    
    asset_timeline = []
    for year in target_years:
        short_digit = str(year)[-1]
        for month_code, month_num in quarterly_months_map.items():
            expiry_day = get_quarterly_expiry_date(year, month_num)
            ticker_code = f"{asset}{month_code}{short_digit}"
            asset_timeline.append({'api_ticker': ticker_code, 'expiry_date': expiry_day})
            
    asset_timeline = sorted(asset_timeline, key=lambda x: x['expiry_date'])
    asset_chunks = []
    current_start_date = datetime(2021, 1, 1).date()
    
    for contract in asset_timeline:
        end_date = contract['expiry_date']
        if current_start_date > datetime.now().date():
            continue
            
        df_single = fetch_moex_history(contract['api_ticker'], session=moex_session)
        if not df_single.empty:
            df_filtered = df_single[(df_single.index >= current_start_date) & (df_single.index <= end_date)]
            if not df_filtered.empty:
                asset_chunks.append(df_filtered)
        current_start_date = end_date + timedelta(days=1)
        
    if asset_chunks:
        continuous_df = pd.concat(asset_chunks).sort_index()
        continuous_df.index = pd.to_datetime(continuous_df.index)
        continuous_df = continuous_df[continuous_df.index.year <= 2026]
        
        asset_path = os.path.join(output_folder, f"{asset}-all-d.txt")
        continuous_df[['Close', 'Ticker']].to_csv(asset_path, sep='\t', index=True, index_label="Date")
        log_message(f"📊 Склейка {asset} завершена. Файл создан: {asset_path}")

moex_session.close()


# =====================================================================
# БЛОК 2: СКЛЕЙКА ЕЖЕМЕСЯЧНЫХ ТОВАРНЫХ ФЬЮЧЕРСОВ (NG и BR)
# =====================================================================
# Для ежемесячных контрактов склейка выполняется по фактическим данным:
# каждый контракт используется до последней доступной даты торгов.
commodity_assets = CONFIG["commodity_assets"]
commodity_codes = CONFIG["commodity_codes"]

moex_session = create_moex_session()

for asset in commodity_assets:
    log_message(f"🔄 Запуск сплошного скачивания и динамической склейки фьючерса {asset}...")
    
    commodity_contracts = []
    for year in target_years:
        short_digit = str(year)[-1]
        for month_code in commodity_codes:
            commodity_contracts.append(f"{asset}{month_code}{short_digit}")
            
    # Загружаем все контракты и сохраняем привязку к тикеру
    downloaded_pools = []
    for ticker in commodity_contracts:
        df_contract = fetch_moex_history(ticker, session=moex_session)
        if not df_contract.empty:
            downloaded_pools.append(df_contract)
    
    if not downloaded_pools:
        log_message(f"⚠️ Пропуск {asset}: не удалось получить исторические таблицы.")
        continue

    # ИСПРАВЛЕНИЕ: Сортировка пулов по первой дате для корректной склейки
    downloaded_pools.sort(key=lambda df: df.index[0])

    commodity_chunks = []
    current_start_date = datetime(2021, 1, 1).date()
    
    for df_single in downloaded_pools:
        last_trading_day = df_single.index[-1]
        if current_start_date > datetime.now().date():
            continue
            
        df_filtered = df_single[(df_single.index >= current_start_date) & (df_single.index <= last_trading_day)]
        if not df_filtered.empty:
            commodity_chunks.append(df_filtered)
            
        current_start_date = last_trading_day + timedelta(days=1)
        
    if commodity_chunks:
        commodity_continuous = pd.concat(commodity_chunks).sort_index()
        commodity_continuous.index = pd.to_datetime(commodity_continuous.index)
        commodity_continuous = commodity_continuous[commodity_continuous.index.year <= 2026]
        
        asset_path = os.path.join(output_folder, f"{asset}-all-d.txt")
        commodity_continuous[['Close', 'Ticker']].to_csv(asset_path, sep='\t', index=True, index_label="Date")
        log_message(f"📊 Склейка {asset} завершена. Файл создан: {asset_path}")

moex_session.close()

log_message("✅ Все файлы фьючерсов записаны в txt файлы.")

# =====================================================================
# БЛОК 3: СКАЧИВАНИЕ ДНЕВНЫХ ЦЕН АКЦИЙ И ИНДЕКСОВ ЗА 5 ЛЕТ (2021–2026)
# =====================================================================
# Эндпоинты MOEX ISS различаются для акций и индексов:
# - Акции: /engines/stock/markets/shares/securities/{ticker}/candles.json
# - Индексы: /engines/stock/markets/index/securities/{ticker}/candles.json
equity_tickers = CONFIG["equity_tickers"]


def fetch_stock_history(ticker, session=None):
    """
    Загружает дневные свечи акции или индекса через MOEX ISS.
    
    Args:
        ticker: Код тикера (например, 'SBER', 'IMOEX').
        session: HTTP-сессия для переиспользования соединения.
    
    Returns:
        pd.DataFrame: DataFrame с колонками [Close, Ticker],
                      индекс — дата (datetime.date).
    """
    clean_ticker = str(ticker).replace('\n', '').replace('\r', '').strip()
    
    base_url = "https://moex.com"
    
    # Эндпоинт для индекса IMOEX отличается от акций
    if clean_ticker == 'IMOEX':
        url = f"{base_url}/iss/engines/stock/markets/index/securities/{clean_ticker}/candles.json"
    else:
        url = f"{base_url}/iss/engines/stock/markets/shares/securities/{clean_ticker}/candles.json"
    
    all_data = []
    start = 0
    page_count = 0
    till_date = datetime.now().date().isoformat()
    own_session = session is None
    
    if own_session:
        session = create_moex_session()

    try:
        while page_count < CONFIG["max_pages"]:
            params = {
                'from': '2021-01-01',
                'till': till_date,
                'interval': 24,
                'start': start
            }
            response = session.get(url, params=params, verify=False, 
                                   timeout=CONFIG["request_timeout"])
            
            if response.status_code != 200:
                log_message(f"⚠️ Ошибка сервера MOEX ISS для {clean_ticker}. Статус: {response.status_code}")
                break

            data = response.json()
            if 'candles' not in data or not data['candles']['data']:
                break

            columns = data['candles']['columns']
            rows = data['candles']['data']
            
            if not rows:
                break
                
            all_data.extend(rows)
            start += len(rows)
            page_count += 1

    except requests.exceptions.RequestException as e:
        log_message(f"❌ Сетевая ошибка при загрузке {clean_ticker}: {e}")
        return pd.DataFrame()
    except (KeyError, ValueError, TypeError) as e:
        log_message(f"❌ Ошибка парсинга данных для {clean_ticker}: {e}")
        return pd.DataFrame()
    except Exception as e:
        log_message(f"❌ Непредвиденная ошибка для {clean_ticker}: {type(e).__name__}: {e}")
        return pd.DataFrame()
    finally:
        if own_session:
            session.close()

    if page_count >= CONFIG["max_pages"]:
        log_message(f"⚠️ Достигнут лимит страниц ({CONFIG['max_pages']}) для {clean_ticker}")

    if not all_data:
        return pd.DataFrame()

    df = pd.DataFrame(all_data, columns=columns)
    df['Date'] = pd.to_datetime(df['begin']).dt.date
    df = df.rename(columns={'close': 'Close'})
    df['Ticker'] = clean_ticker
    df = df[['Date', 'Close', 'Ticker']].drop_duplicates(subset=['Date'])
    
    df.set_index('Date', inplace=True)
    df = df.sort_index()

    if not df.empty:
        df = df[pd.to_datetime(df.index).year <= 2026]

    return df


# Загрузка и запись данных по каждой акции / индексу
moex_session = create_moex_session()

for ticker in equity_tickers:
    log_message(f"📈 Загрузка дневных цен для {ticker} за 2021–2026 гг...")
    df_stock = fetch_stock_history(ticker, session=moex_session)
    if not df_stock.empty:
        file_path = os.path.join(output_folder, f"{ticker}-d-5y.txt")
        df_stock[['Close', 'Ticker']].to_csv(file_path, sep='\t', index=True, index_label="Date")
        log_message(f"Данные {ticker} сохранены: {file_path}")
    else:
        log_message(f"⚠️ Нет данных для {ticker}")

moex_session.close()

log_message("✅ Все данные по акциям и индексам записаны в txt файлы.")

# =====================================================================
# ФИНАЛЬНОЕ СООБЩЕНИЕ
# =====================================================================
log_console_with_timestamp("✅ Загрузка завершена")
