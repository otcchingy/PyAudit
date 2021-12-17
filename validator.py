import re
import argparse

SINGLE_ITEM_REGEX = '^({regex})$'
FLOAT_NUMBER_REGEX = '\d+\.\d+'
INT_NUMBER_REGEX = '\d+'
NUMBER_REGEX = '\d+|(\d+\.\d+)'


def ArgTypeToggle(i):
    if isinstance(i, bool):
        return i
    elif str(i).lower() in ('yes', 'y', 'true', 't', '1'):
        return True
    elif str(i).lower() in ('no', 'n', 'false', 'f', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def ArgTypeYear(i):
    if validate_arg_year(i):
        return i.strip().lower()
    raise argparse.ArgumentTypeError('expected OP[lt(<)|gt(>)|eq(=)]=YEAR ei. lt=2020|gt=1990|eq=1900')


def ArgTypeNumber(i):
    if validate_number()(i):
        return i.strip().lower()
    raise argparse.ArgumentTypeError('expected object type number')


def ArgTypeFloat(i):
    if validate_float_number()(i):
        return i.strip().lower()
    raise argparse.ArgumentTypeError('expected object type float')


def ArgTypeInteger(i):
    if validate_int_number()(i):
        return i.strip().lower()
    raise argparse.ArgumentTypeError('expected object type integer')


def ArgTypeChoice(options: list):
    def Choice(arg):
        if arg.strip().lower() in ' '.join(map(str, options)):
            return arg.strip().lower()
        raise argparse.ArgumentTypeError(f"expected [{'|'.join(map(str, options))}]")

    return Choice


def validate_non_empty_text(value: str):
    return value is not None and len(value.strip()) > 0


def validate_number(*length: int):
    def validate(value: str):
        if len(length) == 0 and re.search(SINGLE_ITEM_REGEX.format(regex=NUMBER_REGEX), value.strip()):
            return True
        for i in length:
            if (i == -1 or (validate_non_empty_text(value) and len(value.strip()) == i)) \
                    and re.search(SINGLE_ITEM_REGEX.format(regex=NUMBER_REGEX), value.strip()):
                return True
        return False

    return validate


def validate_int_number(*length: int):
    def validate(value: str):
        if len(length) == 0 and re.search(SINGLE_ITEM_REGEX.format(regex=INT_NUMBER_REGEX), value.strip()):
            return True
        for i in length:
            if (i == -1 or (validate_non_empty_text(value) and len(value.strip()) == i)) \
                    and re.search(SINGLE_ITEM_REGEX.format(regex=INT_NUMBER_REGEX), value.strip()):
                return True
        return False

    return validate


def validate_float_number(*length: int):
    def validate(value: str):
        if len(length) == 0 and re.search(SINGLE_ITEM_REGEX.format(regex=FLOAT_NUMBER_REGEX), value.strip()):
            return True
        for i in length:
            if (i == -1 or (validate_non_empty_text(value) and len(value.strip()) == i)) \
                    and re.search(SINGLE_ITEM_REGEX.format(regex=FLOAT_NUMBER_REGEX), value.strip()):
                return True
        return False

    return validate


def validate_arg_year(value: str):
    value = value.lower()
    return value[:3] in 'gt= lt= eq=' and validate_number(4)(value[3:])
