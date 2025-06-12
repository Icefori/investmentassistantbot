EXCHANGES_FOREIGN = {"NASDAQ", "AMEX", "LSE", "NYSE"}
EXCHANGES_KZ = {"KASE", "AIX"}

def calc_fees(exchange: str, qty: int, price: float, is_sell: bool = False) -> dict:
    """
    Возвращает словарь с комиссиями: br_fee, ex_fee, cp_fee.
    - exchange: биржа (строка)
    - qty: количество бумаг (int)
    - price: цена одной бумаги (float)
    - is_sell: True если продажа, False если покупка
    """
    exchange = (exchange or "").upper()
    br_fee = 0.0
    ex_fee = 0.0
    cp_fee = 0.0

    if exchange in EXCHANGES_FOREIGN:
        # Покупка
        if not is_sell:
            cp_fee = max(0.01 * qty, 7.5)  # 0.01$ за бумагу, минимум 7.5$
            br_fee = round(0.001 * qty * price, 6)  # 0.1% от суммы сделки
            ex_fee = 0.0
        else:
            # Продажа
            cp_fee = 0.0
            ex_fee = round(0.0001 * qty + 0.000072 * qty, 6)  # NSCC + CAT fee
            br_fee = round(0.001 * qty * price, 6)  # 0.1% от суммы сделки
    elif exchange in EXCHANGES_KZ:
        # KASE, AIX
        br_fee = round(0.0003 * qty * price, 6)  # 0.03% от суммы сделки
        ex_fee = 0.0
        cp_fee = 0.0
    else:
        # По умолчанию комиссии 0
        br_fee = 0.0
        ex_fee = 0.0
        cp_fee = 0.0

    return {
        "br_fee": br_fee,
        "ex_fee": ex_fee,
        "cp_fee": cp_fee
    }