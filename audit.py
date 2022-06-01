import argparse
import copy
import re
from datetime import datetime

import pandas as pd
from soupsieve.pretty import pretty

from validator import ArgTypeToggle, validate_non_empty_text

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)


def is_nan(x):
    return isinstance(x, float) and str(x) == 'nan'


def is_null(x):
    return x is None


def non_nan(x):
    return is_number_str(x) and str(x) != 'nan'


def non_null(x):
    return x is not None


def is_number_str(x, _type=float):
    try:
        if x is None:
            return False
        x = str(x).strip()
        while str(x).startswith('0'):
            x = x[1:]
        _type(x)
        return True
    except:
        return False


def number_from_str(x, _type=float):
    try:
        if x is None:
            return None
        x = str(x).strip()
        while str(x).startswith('0'):
            x = x[1:]
        return _type(x)
    except:
        return None


def make_str_list(text):
    text = str(text).strip()
    if not text.startswith('[') and not text.endswith(']'):
        return None
    text = text[1:-1]
    return [i.strip() for i in text.split(',')]


def read_config(file):
    config = {
        'book': {},
        'bank_statement': {},
        'output': {}
    }

    state = None

    key = None

    value = None

    collect = False

    for data, line in enumerate(file.splitlines()):
        line = line.strip()
        if line.startswith('#') or len(line) == 0:
            continue

        if collect:
            value += f"{'' if value.endswith(',') or value == '[' or line.startswith(',') or line == ']' else ', '}" \
                     f"{line}"
            collect = not value.endswith(']')
            if collect:
                continue

        if line.lower().replace(' ', '').endswith(':'):
            state = line.replace(' ', '').replace(':', '').lower()
            continue

        if '=' in line:
            key, value = tuple(line.split('='))
            if value.startswith('[') and not value.endswith(']'):
                collect = True
            else:
                collect = False

        if not collect:
            if key == 'columns':
                value = make_column_options(value)
            config[state][key] = value

    return config


def get_book_options(config):
    dataframe = pd.read_excel(config['book']['path'], config['book']['sheet'])
    columns_options = config['book']['columns']
    columns = dict()
    for key in columns_options.keys():
        columns[dataframe.columns[key]] = columns_options[key]['key']
    return dataframe, columns


def make_column_options(value):
    value = value[1:-1]
    value = value.split(',')
    result = dict()
    index_count = 0
    for i in value:
        data = i.strip().split(':')
        if not data[0].strip().isnumeric():
            index = index_count
            index_count += 1
        else:
            index = int(data[0].strip())
        column_options = {
            'name': data[1].strip(),
            'key': data[2].strip() if len(data) > 2 else data[1].strip().lower(),
            'rule': data[3].strip() if len(data) > 3 else 'nullable'
        }
        result[index] = column_options
    return result


def analyse_serial_numbers(data):
    checked = set()
    error = set()
    missing = set()
    duplicate = set()

    for i in data:
        if not is_number_str(i, int):
            error.add(i)

    data = sorted([number_from_str(n, int) for n in checked])

    previous = None

    for field in data:
        field = int(field)
        if field in checked:
            duplicate.add(field)
        if previous is not None:
            if previous + 1 != field:
                for i in range(previous + 1, field):
                    missing.add(i)
            previous = field
        else:
            previous = field

        checked.add(field)

    return sorted(error), sorted(duplicate), sorted(missing)


def process_row(config, row):
    uniques = list()
    serials = list()
    columns = config['book']['columns']
    for key in columns.keys():
        value = row[key]
        rule = columns[key]['rule']
        if 'unique' in rule and (not isinstance(value, float) or non_nan(value)):
            uniques.append((columns[key]['key'], value))
        elif 'serial' in rule and (not isinstance(value, float) or non_nan(value)):
            serials.append((columns[key]['key'], value))
    return True if len(serials) == 0 and len(uniques) == 0 else (uniques, serials)


def write_excel(filename, data):
    try:
        writer = pd.ExcelWriter(filename, engine='xlsxwriter')
        data.to_excel(writer, sheet_name='Sheet', index=False)
        writer.save()
    except PermissionError:
        print(f'[x] Error: failed to write to file {filename}. it may still be opened.')


def write_out_new_cashbook_set_from_config(df: pd.DataFrame, config):
    if config.get('output') is not None:
        for filename in config['output'].keys():
            rules = make_str_list(config['output'][filename])
            if len(rules) > 0:
                rule_config = copy.deepcopy(config)
                for rule in rules:
                    column_key = next(filter(lambda x: config['book']['columns'][x]['key'] == rule.split(':')[0],
                                             config['book']['columns'].keys()))
                    rule_config['book']['columns'][column_key]['rule'] = rule.split(':')[1]
                result, _ = clean_book(df, rule_config)
                if len(result) > 0:
                    write_excel(f'{filename}.xlsx', result)


def clean_book(data, config):

    def get_group(rule: str, start_index=0):

        if '(' not in rule and ')' not in 'rule':
            return None

        group_count = None
        from_index = None
        to_index = None

        for i in range(start_index, len(rule)):
            if rule[i] == '(':
                if group_count is None:
                    group_count = 1
                    from_index = i + 1
                else:
                    group_count += 1
            elif group_count is not None and rule[i] == ')':
                group_count -= 1
                if group_count == 0:
                    to_index = i
                    break

        if from_index is None or to_index is None:
            return None

        if not rule[:rule.find('(')].endswith('regex') and \
                (rule.find('&', from_index, to_index) > -1 or rule.find('|', from_index, to_index) > -1):
            return from_index, to_index
        return get_group(rule, to_index)

    def func(_data, _value):
        rule = _value['rule'].replace(' ', '')

        group = get_group(rule, 0)

        if group is not None:
            from_index, to_index = group
            if from_index == 1:
                if len(rule) > to_index + 1:
                    if rule[to_index + 1] == '&':
                        return (func(_data, {'key': _value['key'], 'rule': rule[from_index:to_index]})
                                & func(_data, {'key': _value['key'], 'rule': rule[to_index + 2:]}))
                    elif rule[to_index + 1] == '|':
                        return (func(_data, {'key': _value['key'], 'rule': rule[from_index:to_index]})
                                | func(_data, {'key': _value['key'], 'rule': rule[to_index + 2:]}))
                    else:
                        raise Exception(f"ParseError(expecting [&,|] at {to_index + 1} of rule '{rule}')")
                else:
                    return func(_data, {'key': _value['key'], 'rule': rule[from_index:to_index]})

        if rule.startswith('regex'):
            if '(' in rule and ')' in rule:
                pattern = rule[rule.index('(') + 1:rule.rindex(')')]
                return _data[_value['key']].apply(lambda x: re.compile(pattern).search(str(x)) is not None)
        elif '&' in rule:
            return (func(_data, {'key': _value['key'], 'rule': rule[:rule.index('&')]}) &
                    func(_data, {'key': _value['key'], 'rule': rule[rule.index('&') + 1:]}))
        elif '|' in rule:
            return (func(_data, {'key': _value['key'], 'rule': rule[:rule.index('|')]}) |
                    func(_data, {'key': _value['key'], 'rule': rule[rule.index('|') + 1:]}))
        elif 'nonnull' in rule or 'unique' in rule or 'serial' in rule:
            if '(' in rule and ')' in rule:
                return _data[rule[rule.index('(') + 1:rule.index(')')]].notnull()
            return _data[_value['key']].notnull()
        elif rule.startswith('isnan'):
            if '(' in rule and ')' in rule:
                key = rule[rule.index('(') + 1:rule.index(')')]
                return _data[key].apply(lambda x: is_nan(x))
            return _data[_value['key']].apply(lambda x: is_nan(x))
        elif rule.startswith('nullable'):
            if '(' in rule and ')' in rule:
                key = rule[rule.index('(') + 1:rule.index(')')]
                return _data[key].apply(lambda x: True)
            return _data[_value['key']].apply(lambda x: True)
        elif rule.startswith('isnull'):
            if '(' in rule and ')' in rule:
                key = rule[rule.index('(') + 1:rule.index(')')]
                return _data[key].apply(lambda x: is_null(x))
            return _data[_value['key']].apply(lambda x: is_null(x))
        elif rule.startswith('nonnan'):
            if '(' in rule and ')' in rule:
                key = rule[rule.index('(') + 1:rule.index(')')]
                return _data[key].apply(lambda x: non_nan(x))
            return _data[_value['key']].apply(lambda x: non_nan(x))
        elif rule.startswith('nonnull'):
            if '(' in rule and ')' in rule:
                key = rule[rule.index('(') + 1:rule.index(')')]
                return _data[key].apply(lambda x: non_null(x))
            return _data[_value['key']].apply(lambda x: non_null(x))
        elif rule.startswith('number') or rule.startswith('float'):
            if '(' in rule and ')' in rule:
                key = rule[rule.index('(') + 1:rule.index(')')]
                return _data[key].apply(lambda x:
                                        not (isinstance(x, float) and str(x) == 'nan')
                                        and is_number_str(x))
            return _data[_value['key']].apply(lambda x:
                                              not (isinstance(x, float) and str(x) == 'nan')
                                              and is_number_str(x))
        elif rule.startswith('integer'):
            if '(' in rule and ')' in rule:
                key = rule[rule.index('(') + 1:rule.index(')')]
                return _data[key].apply(lambda x: is_number_str(x, int))
            return _data[_value['key']].apply(lambda x: is_number_str(x, int))
        elif rule.startswith('equals'):
            if '(' in rule and ')' in rule:
                v = rule[rule.index('(') + 1:rule.index(')')]
                return _data[_value['key']].apply(lambda x:
                                                  str(x) == str(v) or str(x).strip() == v.strip())
            raise Exception(f"ParseError(malformed rule '{rule}' for column key '{value['key']}' expecting '(arg)')")
        elif rule.startswith('lesser_than'):
            if '(' in rule and ')' in rule:
                v = rule[rule.index('(') + 1:rule.index(')')]
                return _data[_value['key']].apply(lambda x:
                                                  number_from_str(x) < number_from_str(v)
                                                  if is_number_str(x) and is_number_str(v)
                                                  else str(x) < str(v))
            raise Exception(f"ParseError(malformed rule '{rule}' for column key '{value['key']}') expecting '(arg)')")
        elif rule.startswith('greater_than'):
            if '(' in rule and ')' in rule:
                v = rule[rule.index('(') + 1:rule.index(')')]
                return _data[_value['key']].apply(lambda x:
                                                  number_from_str(x) > number_from_str(v)
                                                  if x is not None and (is_number_str(x) and is_number_str(v))
                                                  else str(x) > str(v))
            raise Exception(f"ParseError(malformed rule '{rule}' for column key '{value['key']}') expecting '(arg)')")
        raise Exception(f"ParseError(unrecognized rule '{rule}' for column key '{value['key']}')")

    indexer = None

    values = config['book']['columns'].values()

    for value in values:

        if indexer is None:
            indexer = func(data, value)
        else:
            indexer = indexer & func(data, value)

    return data[indexer], data[~indexer]


def search_book(data, column, keys):
    def filter_field_contains(_data, _column, _keys):
        return _data[_column].notnull() \
               & (_data[_column].str.lower().str.contains('|'.join(map(lambda x: x.lower().strip(), _keys)))
                  | _data[_column].isin(_keys))

    return data[filter_field_contains(data, column, keys)]


def analyse_unique_references(data, rule):
    checked = set()
    error = set()
    missing = set()
    duplicate = set()

    # TODO: cheques span 50 slips per book find potential missing ranges

    data = sorted([str(r) for r in data])

    group = None
    previous = None

    for field in data:
        if field in checked:
            duplicate.add(field)
        if previous is not None:
            try:
                number = int(field)
                if int(previous) + 1 != number:
                    if abs(number - int(previous) + 1) > 50:
                        pass
                    else:
                        for i in range(previous + 1, number):
                            skipped = str(i)
                            skipped = ('0' * (len(field) - len(skipped))) + str(i)
                            missing.add(skipped)
                previous = number
            except ValueError:
                if group is None or group not in field:
                    for i in range(len(field)):
                        try:
                            previous = int(field[i:].strip())
                            group = field[:i]
                            break
                        except ValueError:
                            pass

                if group is not None and group in field:
                    number = int(field.replace(group, '').strip())
                    if int(previous) + 1 != number:
                        for i in range(previous + 1, number):
                            skipped = group + str(i)
                            skipped = group + ('0' * (len(field) - len(skipped))) + str(i)
                            missing.add(skipped)
                    previous = number
        else:
            try:
                previous = int(field)
            except ValueError:
                error.add(field)

        checked.add(field)

    return sorted(error), sorted(duplicate), sorted(missing)


def analyse_column(data, rule):
    checked = set()
    error = set()
    missing = set()
    duplicate = set()

    # TODO: cheques span 50 slips per book find potential missing ranges

    data = sorted(data)

    group = None
    previous = None

    for field in data:
        if field in checked:
            duplicate.add(field)
        if previous is not None:
            try:
                number = int(field)
                if int(previous) + 1 != number:
                    if abs(number - int(previous) + 1) > 50:
                        pass
                    else:
                        for i in range(previous + 1, number):
                            skipped = str(i)
                            skipped = ('0' * (len(field) - len(skipped))) + str(i)
                            missing.add(skipped)
                previous = number
            except ValueError:
                if group is None or group not in field:
                    for i in range(len(field)):
                        try:
                            previous = int(field[i:].strip())
                            group = field[:i]
                            break
                        except ValueError:
                            pass

                if group is not None and group in field:
                    number = int(field.replace(group, '').strip())
                    if int(previous) + 1 != number:
                        for i in range(previous + 1, number):
                            skipped = group + str(i)
                            skipped = group + ('0' * (len(field) - len(skipped))) + str(i)
                            missing.add(skipped)
                    previous = number
        else:
            try:
                previous = int(field)
            except ValueError:
                error.add(field)

        checked.add(field)

    return sorted(error), sorted(duplicate), sorted(missing)


def audit(config, book: pd.DataFrame):
    uniques = dict()
    serials = dict()

    for _, row in book.iterrows():
        result = process_row(config, row)
        if isinstance(result, bool) and result:
            continue
        elif isinstance(result, tuple):
            u, s = result
            for column, _ in u:
                if column not in uniques:
                    uniques[column] = list()
                uniques[column].append(row[column])
            for column, _ in s:
                if column not in serials:
                    serials[column] = list()
                serials[column].append(row[column])

    logs = {}

    # TODO: analysis here

    for key, value in serials.items():
        error, duplicate, missing = analyse_serial_numbers(value)
        logs['serial'] = {'error': error, 'duplicate': duplicate, 'missing': missing}
    for key, value in uniques.items():
        rule_for_key = next(filter(lambda x: x['key'] == key, config['book']['columns'].values()))['rule']
        error, duplicate, missing = analyse_unique_references(value, rule_for_key)
        logs['unique'] = {'error': error, 'duplicate': duplicate, 'missing': missing}
    return logs


def args_parser():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", type=str, required=False,
                    help=f'path to config file')

    ap.add_argument("-cp", "--cashbook-path", type=str, required=False,
                    help="cashbook <path> name")
    ap.add_argument("-cs", "--cashbook-sheet", type=str, required=False,
                    help="cashbook <sheet> name in excel")
    ap.add_argument("-cc", "--cashbook-columns", type=str, nargs='?', required=False,
                    help="cashbook column options")
    ap.add_argument("-sp", "--statement-path", type=str, required=False,
                    help="statement <path> name")
    ap.add_argument("-ss", "--statement-sheet", type=str, required=False,
                    help="statement <sheet> name in excel")
    ap.add_argument("-sc", "--statement-columns", type=str, nargs='?', required=False,
                    help="statement column options")

    ap.add_argument("-a", "--analyse", type=ArgTypeToggle, nargs='?', default=True, required=False,
                    help=f"analyse resulting cashbook")

    ap.add_argument("-s", "--search", type=str, nargs='?', required=False,
                    help=f"keys to match in book eg. --search [column-key] [search-keys...]")

    ap.add_argument("-o", "--output", type=str, nargs='?', required=False,
                    help="output file path")

    ap.add_argument("-v", "--verbose", type=ArgTypeToggle, default=False, required=False,
                    help="show process output")

    return vars(ap.parse_args())


if __name__ == '__main__':

    args = args_parser()

    # args['config'] = 'config-2021.ini'
    # args['analyse'] = True
    # args['verbose'] = True
    # args['output'] = 'account_2021.'
    # args['search'] = ['description', 'pendrives']

    # for _key in args.keys():
    #     if isinstance(args[_key], dict):
    #         for k in args[_key].keys():
    #             print(_key + '.' + k, ':', args[_key][k])
    #     else:
    #         print(_key, ':', args[_key])
    # print('\n\n')

    if not args['config'] and \
            (not args['cashbook_path'] or not args['cashbook_sheet'] or not args['cashbook_columns']):
        print('[X] You did not specify some config options')
        print('[*] enter your options for the following config...')
        for _row in ['cashbook_path', 'cashbook_sheet', 'cashbook_columns']:
            if args[_row] is None or len(args[_row]) == 0:
                args[_row] = input('[i] ' + _row.replace('_', ' ') + ': ').strip()
                if _row == 'cashbook_columns':
                    try:
                        args[_row] = make_column_options(args[_row])
                        print(args[_row])
                    except KeyError:
                        args[_row] = None
                while args[_row] is None or len(args[_row]) == 0:
                    args[_row] = input('[i] ' + _row.replace('_', ' ') + ': ').strip()
                    if _row == 'cashbook_columns':
                        try:
                            args[_row] = make_column_options(args[_row])
                            print(args[_row])
                        except KeyError:
                            args[_row] = None

    if validate_non_empty_text(args.get('config')):
        assert args['config'].endswith(".ini")
        _config = read_config(open(args['config'], 'r').read())
    else:
        assert args['cashbook_path'] is not None
        assert args['cashbook_sheet'] is not None
        assert args['cashbook_columns'] is not None
        _config = {
            'book': {
                'path': args['cashbook_path'],
                'sheet': args['cashbook_sheet'],
                'columns': args['cashbook_columns'],
            },
            'statement': {
                'path': args.get('statement_path'),
                'sheet': args.get('statement_sheet'),
                'columns': args.get('statement_columns'),
            }
        }
        if args.get('extra_config') is not None:
            for _arg in args['extra_config']:
                if ':' in args:
                    _k, _v = tuple(_arg.split(':'))
                    _config[f'{_k.strip().lower()}'] = _v.strip()
                else:
                    if args['verbose']:
                        print(f"[*] could not add '{_arg}' to your config. input must be of form 'key:value'")

    # for _key in _config.keys():
    #     print('\n' + _key)
    #     for sub_key in _config[_key].keys():
    #         print(sub_key, ':', _config[_key][sub_key])
    # print('\n\n')

    book_dataframe, column_names = get_book_options(_config)
    book_dataframe = book_dataframe.rename(columns=column_names)
    write_out_new_cashbook_set_from_config(book_dataframe[column_names.values()], _config)

    print("DATAFRAME SIZE:", len(book_dataframe))

    results, entry_errors = clean_book(
        data=book_dataframe,
        config=_config
    )

    print("DATAFRAME AFTER CLEANING WITH RULES:", len(results))
    print("DATAFRAME ERRORS AFTER CLEANING:", len(entry_errors))

    if 'search' in args and args['search'] is not None and len(args['search']) > 1:
        results = search_book(
            data=results,
            column=args['search'][0],
            keys=args['search'][1:]
        )

    print("DATAFRAME AFTER SEARCHED:", len(results))

    if len(results) > 0:

        date_time_now = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

        if args['verbose']:
            print('\n\nDATAFRAME:')

        if validate_non_empty_text(args['output']) and args['search'] is not None:

            output_path = args['output'].strip()

            if output_path[-1] == '.':
                name = f'{output_path[:-1]}-' if len(output_path[:-1]) > 0 else ''
                output_path = f"{name}output-{date_time_now}.xlsx"

            if args['verbose']:
                for index, _row in results.iterrows():
                    row_out = ""
                    for column in column_names.values():
                        row_out = f'{row_out} {_row[column]}'
                    print('[$]', index, row_out)
                print('Total Results:', len(results))
            write_excel(output_path, results.filter(column_names.values(), axis=1))

        else:
            if args['verbose']:
                for index, _row in results.iterrows():
                    row_out = ""
                    for column in column_names.values():
                        row_out = f'{row_out} {_row[column]}'
                    print('[$]', index, row_out)
                print('Total Results:', len(results))
            else:
                output_path = f'output-{date_time_now}.xlsx'
                write_excel(output_path, results.filter(column_names.values(), axis=1))

        if args['verbose']:
            print('\n\nANALYSIS"')

        if args['analyse']:

            _logs = audit(_config, results)

            # TODO: get column rule and analysis

            if validate_non_empty_text(args['output']):
                output_path = args['output'].strip()

                # search_book(data=results, column=column, keys=keys)
                if output_path[-1] == '.':
                    name = f'{output_path[:-1]}-' if len(output_path[:-1]) > 0 else ''
                    output_path = f"analysis-{name}output-{date_time_now}.txt"
                    with open(output_path, 'w') as file:
                        print(pretty(_logs), file=file)

                if args['verbose']:
                    print(pretty(_logs))

    print('\n\n[X] DONE. PROGRAM EXITING...')
