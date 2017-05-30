import unittest
import pymysql
import tap_mysql
import copy
import singer
import os


DB_NAME='tap_mysql_test'

def get_test_connection():

    creds = {}
    creds['host'] = os.environ.get('SINGER_TAP_MYSQL_TEST_DB_HOST')
    creds['user'] = os.environ.get('SINGER_TAP_MYSQL_TEST_DB_USER')
    creds['password'] = os.environ.get('SINGER_TAP_MYSQL_TEST_DB_PASSWORD')
    if not creds['password']:
        del creds['password']

    con = pymysql.connect(**creds)

    try:
        with con.cursor() as cur:
            try:
                cur.execute('DROP DATABASE {}'.format(DB_NAME))
            except:
                pass
            cur.execute('CREATE DATABASE {}'.format(DB_NAME))
    finally:
        con.close()

    creds['database'] = DB_NAME

    return pymysql.connect(**creds)


class TestTypeMapping(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        con = get_test_connection()

        with con.cursor() as cur:
            cur.execute('''
            CREATE TABLE test_type_mapping (
            c_pk INTEGER PRIMARY KEY,
            c_decimal DECIMAL,
            c_decimal_2 DECIMAL(11, 2),
            c_tinyint TINYINT,
            c_smallint SMALLINT,
            c_mediumint MEDIUMINT,
            c_int INT,
            c_bigint BIGINT,
            c_float FLOAT,
            c_double DOUBLE,
            c_bit BIT(4)
            )''')

            discovered = tap_mysql.discover_schemas(con)

            cls.schema = discovered['streams'][0]['schema']


    def test_decimal(self):
        self.assertEqual(self.schema['properties']['c_decimal'], {
            'type': 'number',
            'inclusion': 'available',
            'exclusiveMaximum': 10000000000,
            'multipleOf': 1
        })

    def test_decimal_with_defined_scale_and_precision(self):
        self.assertEqual(self.schema['properties']['c_decimal_2'], {
            'type': 'number',
            'inclusion': 'available',
            'exclusiveMaximum': 1000000000,
            'multipleOf': 0.01})

    def test_tinyint(self):
        self.assertEqual(self.schema['properties']['c_tinyint'], {
            'type': 'integer',
            'inclusion': 'available',
            'minimum': -128,
            'maximum': 127
        })

    def test_smallint(self):
        self.assertEqual(self.schema['properties']['c_smallint'], {
            'type': 'integer',
            'inclusion': 'available',
            'minimum': -32768,
            'maximum':  32767
        })

    def test_mediumint(self):
        self.assertEqual(self.schema['properties']['c_mediumint'], {
            'type': 'integer',
            'inclusion': 'available',
            'minimum': -8388608,
            'maximum':  8388607
        })

    def test_int(self):
        self.assertEqual(self.schema['properties']['c_int'], {
            'type': 'integer',
            'inclusion': 'available',
            'minimum': -2147483648,
            'maximum': 2147483647
        })

    def test_bigint(self):
        self.assertEqual(self.schema['properties']['c_bigint'], {
            'type': 'integer',
            'inclusion': 'available',
            'minimum': -9223372036854775808,
            'maximum':  9223372036854775807
        })

    def test_float(self):
        self.assertEqual(self.schema['properties']['c_float'], {
            'type': 'number',
            'inclusion': 'available',
        })


    def test_double(self):
        self.assertEqual(self.schema['properties']['c_double'], {
            'type': 'number',
            'inclusion': 'available',
        })

    def test_bit(self):
        self.assertEqual(self.schema['properties']['c_bit'], {
            'inclusion': 'unsupported',
            'description': 'Unsupported column type bit(4)',
        })

    def test_pk(self):
        self.assertEqual(
            self.schema['properties']['c_pk']['inclusion'],
            'automatic')


class TestIndexDiscoveredSchema(unittest.TestCase):

    def setUp(self):
        con = get_test_connection()

        try:
            with con.cursor() as cur:
                cur.execute('''
                    CREATE TABLE tab (
                      a INTEGER,
                      b INTEGER)
                ''')

                self.discovered = tap_mysql.discover_schemas(con)
        finally:
            con.close()

    def runTest(self):
        discovered = copy.deepcopy(self.discovered)
        print(tap_mysql.index_schema(discovered))
        self.assertEqual(
            tap_mysql.index_schema(discovered),
            {
                "tap_mysql_test": {
                    "tab": {
                        "b": {
                            "inclusion": "available",
                            "type": "integer",
                            "maximum": 2147483647,
                            "minimum": -2147483648
                        },
                        "a": {
                            "inclusion": "available",
                            "type": "integer",
                            "maximum": 2147483647,
                            "minimum": -2147483648
                        }
                    }
                }
            },
            'makes nested structure from flat discovered schemas')


class TestSelectsAppropriateColumns(unittest.TestCase):

    def runTest(self):
        selected_cols = ['a', 'b', 'd']
        indexed_schema = {'some_db':
                          {'some_table':
                           {'a': {'inclusion': 'available'},
                            'b': {'inclusion': 'unsupported'},
                            'c': {'inclusion': 'automatic'}}}}

        expected_pruned_schema = {'some_db':
                                  {'some_table':
                                   {'a': {'inclusion': 'available'},
                                    'c': {'inclusion': 'automatic'}}}}

        tap_mysql.remove_unwanted_columns(selected_cols,
                                          indexed_schema,
                                          'some_db',
                                          'some_table')

        self.assertEqual(indexed_schema,
                         expected_pruned_schema,
                         'Keep automatic as well as selected, available columns.')

class TestSchemaMessages(unittest.TestCase):

    def runTest(self):
        con = get_test_connection()
        try:
            with con.cursor() as cur:
                cur.execute('''
                    CREATE TABLE tab (
                      id INTEGER PRIMARY KEY,
                      a INTEGER,
                      b INTEGER)
                ''')

            selections = tap_mysql.discover_schemas(con)
            selections['streams'][0]['selected'] = True
            selections['streams'][0]['schema']['properties']['a']['selected'] = True
            messages = list(tap_mysql.generate_messages(con, selections, {}))
            schema_message = messages[0]
            self.assertTrue(isinstance(schema_message, singer.SchemaMessage))
            self.assertEqual(schema_message.schema['properties'].keys(), set(['id', 'a']))

        finally:
            con.close()