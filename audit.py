# This is a sample Python script.

# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
import argparse
from datetime import datetime
import pandas as pd

from validator import ArgTypeToggle, validate_non_empty_text, validate_number

pd.set_option('display.max_rows', None)
pd.set_option('display.max_columns', None)


def is_not_nan(field):
    return str(field) != 'nan'


def is_valid_entry(row):
    return str(row['payee']) != 'nan' and str(row['date']) != 'nan'


def is_debit(row):
    return (isinstance(row['debit'], int) or isinstance(row['debit'], float)) and str(row['debit']) != 'nan'


def is_credit(row):
    return (isinstance(row['credit'], int) or isinstance(row['credit'], float)) and str(row['credit']) != 'nan'


def is_cashbook_entry(row):
    return is_valid_entry(row) and (is_credit(row) or is_debit(row))


def read_config(file):
    config = {
        'cashbook': {

        },
        'bank_statement': {

        },
        'new_cashbook_set': {

        }
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
        column_options = {'title': data[1].strip(), 'description': data[2].strip()}
        result[index] = column_options
    return result


def analyse_pv_numbers(data):
    checked = set()
    error = set()
    missing = set()
    duplicate = set()

    for i in data:
        try:
            if str(float(i)).endswith('.0'):
                checked.add(i)
            else:
                error.add(str(i))
        except ValueError:
            error.add(str(i))

    data = sorted([int(i) for i in checked])

    previous = None

    for field in data:
        if field in checked:
            duplicate.add(field)
        if previous is not None:
            try:
                number = int(field)
                if int(previous) + 1 != number:
                    for i in range(previous + 1, number):
                        missing.add(i)
                previous = number
            except ValueError:
                error.add(field)
                previous = previous + 1
        else:
            try:
                previous = int(field)
            except ValueError:
                error.add(field)

        checked.add(field)

    return sorted(error), sorted(duplicate), sorted(missing)


def analyse_references(data):
    checked = set()
    error = set()
    missing = set()
    duplicate = set()

    # TODO: cheques span 50 slips per book find potential missing ranges

    data = sorted(data)

    def find_missing():
        groups = []
        start = None
        g = []
        for i in data:
            if len(g) > 0:
                if abs(int(start) - int(i)) > 50:
                    groups.append(g)
                    start = i  # if next starts 1 or 6
                    g = []
            else:
                if start.endswith('1') or start.endswith('6'):
                    start = i
                else:
                    start = int(i) % 5

            g.append(i)

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


def audit(cashbook_df: pd.DataFrame):
    # TODO: load bank statements

    pv_number_list = []
    reference_list = []

    other = list()

    for index, row in cashbook_df.iterrows():
        if is_cashbook_entry(row):
            if is_credit(row):
                if is_not_nan(row['pv-number']):
                    pv_number_list.append(str(row['pv-number']))
                else:
                    other.append(row)

                if is_not_nan(row['reference']):
                    reference_list.append(str(row['reference']))
                else:
                    other.append(row)

            elif is_debit(row):
                # check in cashbook
                pass
            else:
                other.append(row)

    return analyse_pv_numbers(pv_number_list), analyse_references(reference_list), other


def write_out_new_cashbook_set_from_config(df: pd.DataFrame, config):
    if config.get('new_cashbook_set') is not None:
        for group in config['new_cashbook_set'].keys():
            pvs = eval(config['new_cashbook_set'][group])
            if len(pvs) > 0:
                result = df[df['pv-number'].isin([str(i) for i in pvs])]
                write_excel(f'{group}.xlsx', result)


def write_excel(filename, data):
    writer = pd.ExcelWriter(filename, engine='xlsxwriter')
    data.to_excel(writer, sheet_name='CashBook', index=False)
    writer.save()


def get_cashbook_options(config):
    cashbook_df = pd.read_excel(config['cashbook']['path'], config['cashbook']['sheet'])
    columns_options = config['cashbook']['columns']
    columns_map = dict()
    for i in columns_options.keys():
        columns_map[cashbook_df.columns[i]] = columns_options[i]['description']
    return cashbook_df, columns_map


def filter_field_contains(data, column, keys):
    return data[column].notnull() \
           & data[column].str.lower().str.contains('|'.join(map(lambda x: x.lower().strip(), keys)))


def search_cashbook(**kwargs):
    # search using columns
    data = kwargs['data']
    date = kwargs.get('date')
    search = kwargs.get('search')
    pv_number = kwargs.get('pv_number')
    reference = kwargs.get('reference')
    payee = kwargs.get('payee')
    description = kwargs.get('description')
    credit = kwargs.get('credit')
    debit = kwargs.get('debit')
    balance = kwargs.get('balance')

    if search is not None and len(search) > 0:
        data = data[
            filter_field_contains(data, 'date', search) |
            filter_field_contains(data, 'pv-number', search) |
            filter_field_contains(data, 'reference', search) |
            filter_field_contains(data, 'payee', search) |
            filter_field_contains(data, 'debit', search) |
            filter_field_contains(data, 'credit', search) |
            filter_field_contains(data, 'balance', search) |
            filter_field_contains(data, 'description', search)
            ]
        print('DATA: ', len(data))

    if pv_number is not None and len(pv_number) > 0:
        data = data[data['pv-number'].notnull() & data['pv-number'].isin(pv_number)]
        print('DATA: ', len(data))

    if reference is not None and len(reference) > 0:
        data = data[data['reference'].notnull() & data['reference'].isin(reference)]
        print('DATA: ', len(data))

    if payee is not None and len(payee) > 0:
        data = data[filter_field_contains(data, 'payee', payee)]
        print('DATA: ', len(data))

    if description is not None and len(description) > 0:
        data = data[filter_field_contains(data, 'description', description)]
        print('DATA: ', len(data))

    if date is not None and len(date) > 0:
        print(date)
        print('DATA: ', len(data))

    if credit is not None and len(credit) > 0:
        print(credit)
        print('DATA: ', len(data))

    if debit is not None and len(debit) > 0:
        print(debit)
        print('DATA: ', len(data))

    if balance is not None and len(balance) > 0:
        print(balance)
        print('DATA: ', len(data))

    # newdf = df[(df.origin == "JFK") & (df.carrier == "B6")]
    # newdf = df.query('origin == "JFK" & carrier == "B6"')
    # newdf = df.loc[(df.origin == "JFK") | (df.origin == "LGA")]
    # newdf = df[df.origin.isin(["JFK", "LGA"])]
    # newdf = df.loc[(df.origin != "JFK") & (df.carrier == "B6")]
    # newdf = df[~((df.origin == "JFK") & (df.carrier == "B6"))]
    # df[df['var1'].str[0] == 'A']
    # df[df['var1'].str.len() > 3]
    # df[df['var1'].str.contains('A|B')]
    # l1 = list(filter(lambda x: x["origin"] == 'JFK' and x["carrier"] == 'B6', lst_df))
    # newdf = df[df.apply(lambda x: x["origin"] == 'JFK' and x["carrier"] == 'B6', axis=1)]

    return data


def make_filter_comparator(data, column, param, value_func):
    if ':' in param:
        op, value = tuple(param.strip().split(':'))
        op = op.lower().strip()
        value = value_func(value.strip())
        assert op == 'eq' or op == 'lt' or op == 'gt'
        return data[column].notnull() & (data[column] < value
                                         if op == 'lt' else data[column] > value
        if op == 'gt' else data[column] == value)
    else:
        return data


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
                    help=f"keys to match in all cashbook field")
    ap.add_argument("-dt", "--date", type=str, nargs='+', required=False,
                    help="date search param [eq:dd/mm/yyyy or eq:dd/mm/yyyy or 'gt:dd/mm/yyyy [and|or] lt:dd/mm/yy]'")
    ap.add_argument("-pv", "--pv-number", type=int, nargs='+', required=False,
                    help=f"list of pv numbers")
    ap.add_argument("-py", "--payee", type=str, nargs='+', required=False,
                    help=f"list of payee search args")
    ap.add_argument("-rf", "--reference", type=str, nargs='+', required=False,
                    help="list of transaction references")
    ap.add_argument("-cd", "--credit", type=str, nargs='+', required=False,
                    help="amount search param for credit [eq:number or gt:number [and|or] lt:number]")
    ap.add_argument("-db", "--debit", type=str, nargs='+', required=False,
                    help="amount search param for debit [eq:number or gt:number [and|or] lt:number]")
    ap.add_argument("-bl", "--balance", type=str, nargs='+', required=False,
                    help="amount search param for balance [eq:number or gt:number [and|or] lt:number]")
    ap.add_argument("-dc", "--description", type=str, nargs='+', required=False,
                    help="list of descriptive search args")

    ap.add_argument("-o", "--output", type=str, nargs='?', required=False,
                    help="output file path")
    ap.add_argument("-v", "--verbose", type=ArgTypeToggle, default=False, required=False,
                    help="show process output")

    return vars(ap.parse_args())


# Press the green button in the gutter to run the script.
if __name__ == '__main__':

    args = args_parser()

    args['config'] = 'config-revenue.ini'
    args['analyse'] = True
    args['verbose'] = True
    args['output'] = 'account_revenue_2021.'
    # args['pv_number'] = None  # [1,2,3]
    # args['reference'] = None  # ['016779', '016780', '693615', 'TRF/19/35']
    # args['description'] = ['imprest']
    # args['payee'] = None  # ['fpmu']
    # args['search'] = ['2019-12']
    # args['date'] = ['gt:09/05/2019 and lt:05/09/2019', 'or', 'eq:12/12/2019']

    # for key in args.keys():
    #     if isinstance(args[key], dict):
    #         for k in args[key].keys():
    #             print(key + '.' + k, ':', args[key][k])
    #     else:
    #         print(key, ':', args[key])
    # print('\n\n')

    if not args['config'] and \
            (not args['cashbook_path'] or not args['cashbook_sheet'] or not args['cashbook_columns']):
        print('[X] You did not specify some config options')
        print('[*] enter your options for the following config...')
        for i in ['cashbook_path', 'cashbook_sheet', 'cashbook_columns']:
            if args[i] is None or len(args[i]) == 0:
                args[i] = input('[i] ' + i.replace('_', ' ') + ': ').strip()
                if i == 'cashbook_columns':
                    try:
                        args[i] = make_column_options(args[i])
                        print(args[i])
                    except Exception:
                        args[i] = None
                while args[i] is None or len(args[i]) == 0:
                    args[i] = input('[i] ' + i.replace('_', ' ') + ': ').strip()
                    if i == 'cashbook_columns':
                        try:
                            args[i] = make_column_options(args[i])
                            print(args[i])
                        except Exception:
                            args[i] = None

    if validate_non_empty_text(args.get('config')):
        assert args['config'].endswith(".ini")
        _config = read_config(open(args['config'], 'r').read())
    else:
        assert args['cashbook_path'] is not None
        assert args['cashbook_sheet'] is not None
        assert args['cashbook_columns'] is not None
        _config = {
            'cashbook': {
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
            for arg in args['extra_config']:
                if ':' in args:
                    k, v = tuple(arg.split(':'))
                    _config[f'{k.strip().lower()}'] = v.strip()
                else:
                    if args['verbose']:
                        print(f"[*] could not add '{arg}' to your config. input must be of form 'key:value'")

    # for key in _config.keys():
    #     print('\n' + key)
    #     for k in _config[key].keys():
    #         print(k, ':', _config[key][k])
    # print('\n\n')

    cashbook_dataframe, column_names = get_cashbook_options(_config)
    cashbook_dataframe = cashbook_dataframe.rename(columns=column_names)
    write_out_new_cashbook_set_from_config(cashbook_dataframe[column_names.values()], _config)

    results = search_cashbook(
        data=cashbook_dataframe,
        # date=args['date'],
        # credit=args['credit'],
        # debit=args['debit'],
        # balance=args['balance'],
        pv_number=args['pv_number'],
        reference=args['reference'],
        payee=args['payee'],
        description=args['description'],
        search=args['search']
    )

    # todo: check if search parameter available before write out file

    if len(results) > 0:

        date_time_now = datetime.now().strftime('%Y-%m-%d-%H-%M-%S')

        if args['analyse']:

            pv_analysis, reference_analysis, other = audit(results)

            if validate_non_empty_text(args['output']):
                output_path = args['output'].strip()

                if output_path[-1] == '.':
                    name = f'{output_path[:-1]}-' if len(output_path[:-1]) > 0 else ''
                    output_path = f"analysis-{name}output-{date_time_now}.txt"
                    with open(output_path, 'w') as file:
                        error, duplicate, missing = pv_analysis
                        file.write('# PV Analysis\n')
                        file.write('Error:\n')
                        file.write(', '.join([str(i) for i in error]) + '\n')
                        if len(error) > 0:
                            for index, i in search_cashbook(data=results, pv_number=error).iterrows():
                                print('[$]', index, i['date'], i['pv-number'], i['reference'], i['payee'], i['credit'],
                                      i['debit'], i['description'], file=file)
                        file.write('\n\n')

                        file.write('Duplicate:\n')
                        file.write(', '.join([str(i) for i in duplicate]) + '\n')
                        if len(duplicate) > 0:
                            for index, i in search_cashbook(data=results, pv_number=duplicate).iterrows():
                                print('[$]', index, i['date'], i['pv-number'], i['reference'], i['payee'], i['credit'],
                                      i['debit'], i['description'], file=file)
                        file.write('\n\n')

                        file.write('Missing:\n')
                        file.write(', '.join([str(i) for i in missing]))

                        file.write('\n\n\n\n')

                        error, duplicate, missing = reference_analysis
                        file.write('# Reference Analysis\n')
                        file.write('Error:\n')
                        file.write(', '.join([str(i) for i in error]) + '\n')
                        if len(error) > 0:
                            for index, i in search_cashbook(data=results, reference=error).iterrows():
                                print('[$]', index, i['date'], i['pv-number'], i['reference'], i['payee'], i['credit'],
                                      i['debit'], i['description'], file=file)
                        file.write('\n\n')
                        file.write('Duplicate:\n')
                        file.write(', '.join([str(i) for i in duplicate]) + '\n')
                        if len(duplicate) > 0:
                            for index, i in search_cashbook(data=results, reference=duplicate).iterrows():
                                print('[$]', index, i['date'], i['pv-number'], i['reference'], i['payee'], i['credit'],
                                      i['debit'], i['description'], file=file)
                        file.write('\n\n')
                        file.write('Missing:\n')
                        file.write(', '.join(missing))
                        print('Missing:', len(missing))

                        file.write('\n\n\n\n')
                        file.write('# Others:\n')
                        for i in other:
                            print('[$]', i['date'], i['pv-number'], i['reference'], i['payee'], i['credit'],
                                  i['debit'], i['description'], file=file)

            if args['verbose']:
                error, duplicate, missing = pv_analysis
                print('Errors:', error, '\n')
                print('Duplicates:', duplicate, '\n')
                print('Missing:', missing, '\n')
                print('\n\n')

                error, duplicate, missing = reference_analysis
                print('Errors:', error, '\n')
                print('Duplicates:', duplicate, '\n')
                print('Missing:', missing, '\n')
                print('\n\n')

                print('Others:', '\n')
                for row in other:
                    print(row['date'], row['pv-number'], row['payee'],
                          row['credit'], row['description'])
                print('\n\n')

        results = results[results['date'].notnull() & results['payee'].notnull()]

        if args['verbose']:
            print('\n\n')

        if validate_non_empty_text(args['output']) and not (
                args['search'] is None and args['date'] is None and args['pv_number'] is None
                and args['payee'] is None and args['reference'] is None and args['credit'] is None
                and args['debit'] is None and args['balance'] is None and args['description'] is None):

            output_path = args['output'].strip()

            if output_path[-1] == '.':
                name = f'{output_path[:-1]}-' if len(output_path[:-1]) > 0 else ''
                output_path = f"{name}output-{date_time_now}.xlsx"

            if args['verbose']:
                for index, i in results.iterrows():
                    print('[$]', index, i['date'], i['pv-number'], i['reference'], i['payee'], i['credit'],
                          i['debit'], i['description'])
                print('Total Results:', len(results))
            write_excel(output_path, results.filter(column_names.values(), axis=1))

        else:
            if args['verbose']:
                for index, i in results.iterrows():
                    print('[$]', index, i['date'], i['pv-number'], i['reference'], i['payee'], i['credit'],
                          i['debit'], i['description'])
                print('Total Results:', len(results))
            else:
                output_path = f'output-{date_time_now}.xlsx'
                write_excel(output_path, results.filter(column_names.values(), axis=1))

    print('\n\n[X] DONE. PROGRAM EXITING...')
