"""Conservative amount parsing. Ambiguous single 3-digit separators stay unknown."""
import re
from decimal import Decimal, InvalidOperation


def parse_number(value, decimal_separator=None, percentage=False):
    if value is None or isinstance(value, bool):
        return None
    s = str(value).strip().replace('\u2212', '-').replace('\u00a0', ' ')
    if not s or s.lower() in {'null', 'none', 'n/a', 'na', '-', '—', '–'}:
        return None
    negative = s.startswith(('(', '[')) and s.endswith((')', ']'))
    if negative:
        s = s[1:-1].strip()
    s = re.sub(r'^(?:USD|EUR|GBP|INR|MYR|RM|Rs\.?|[$€£₹¥])\s*', '', s, flags=re.I)
    s = re.sub(r'\s*(?:USD|EUR|GBP|INR|MYR|RM)$', '', s, flags=re.I)
    if s.endswith('%'):
        if not percentage:
            return None
        s = s[:-1].strip()
    if not re.fullmatch(r'[+-]?\d[\d,. ]*', s):
        return None
    if ' ' in s:
        if not re.fullmatch(r'[+-]?\d{1,3}(?: \d{3})+(?:[.,]\d+)?', s):
            return None
        s = s.replace(' ', '')
    if decimal_separator:
        group = ',' if decimal_separator == '.' else '.'
        if group in s:
            integer = s.split(decimal_separator)[0]
            if not re.fullmatch(r'[+-]?\d{1,3}(?:' + re.escape(group) + r'\d{3})+', integer) and not (
                group == ',' and re.fullmatch(r'[+-]?\d{1,2}(?:,\d{2})*,\d{3}', integer)):
                return None
            s = s.replace(group, '')
        s = s.replace(decimal_separator, '.')
    elif ',' in s and '.' in s:
        return parse_number(value, '.' if s.rfind('.') > s.rfind(',') else ',', percentage)
    elif ',' in s or '.' in s:
        sep = ',' if ',' in s else '.'
        tail = s.split(sep)[-1]
        if s.count(sep) == 1 and len(tail) in (1, 2):
            s = s.replace(sep, '.')
        elif re.fullmatch(r'[+-]?\d{1,3}(?:' + re.escape(sep) + r'\d{3}){2,}', s):
            s = s.replace(sep, '')
        elif sep == ',' and re.fullmatch(r'[+-]?\d{1,2}(?:,\d{2})+,\d{3}', s):
            s = s.replace(',', '')
        else:
            return None
    try:
        result = Decimal(s)
        if not result.is_finite():
            return None
        return -abs(result) if negative else result
    except InvalidOperation:
        return None


def infer_decimal_separator(text):
    comma = len(re.findall(r'\b\d+,\d{2}(?!\d)', text))
    point = len(re.findall(r'\b\d+\.\d{2}(?!\d)', text))
    if comma and not point:
        return ','
    if point and not comma:
        return '.'
    return None
