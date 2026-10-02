from decimal import Decimal


def decimal_text(value:Decimal)->str:
    text=format(value,'f')
    if '.' in text:text=text.rstrip('0').rstrip('.')
    return '0' if text in ('','-0') else text
