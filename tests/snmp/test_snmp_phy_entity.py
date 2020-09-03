import logging
import pytest
import time

from tests.common.utilities import wait_until

pytestmark = [
    pytest.mark.topology('any'),
    pytest.mark.device_type('vs')
]

STATE_DB = 6
TABLE_NAME_SEPARATOR_VBAR = '|'

# From RFC 2737, 1 means replaceable, 2 means not replaceable
REPLACEABLE = 1
NOT_REPLACEABLE = 2

# Physical Class From RFC 2737
PHYSICAL_CLASS_OTHER = 1
PHYSICAL_CLASS_UNKNOWN = 2
PHYSICAL_CLASS_CHASSIS = 3
PHYSICAL_CLASS_BACKPLANE = 4
PHYSICAL_CLASS_CONTAINER = 5
PHYSICAL_CLASS_POWERSUPPLY = 6
PHYSICAL_CLASS_FAN = 7
PHYSICAL_CLASS_SENSOR = 8
PHYSICAL_CLASS_MODULE = 9
PHYSICAL_CLASS_PORT = 10
PHYSICAL_CLASS_STACK = 11

# Chassis Constants
CHASSIS_OID = 1
CHASSIS_MGMT_OID = 200000000
CHASSIS_THERMAL_OFFSET = 100000
CHASSIS_KEY = 'chassis 1'

# Fan Drawer Constants
FAN_DRAWER_KEY_TEMPLATE = 'FAN_DRAWER_INFO|{}'
FAN_DRAWER_BASE_SUB_ID = 500000000
FAN_DRAWER_POSITION_MULTIPLE = 1000000

# Fan Constants
FAN_KEY_TEMPLATE = 'FAN_INFO|{}'
FAN_POSITION_MULTIPLE = 20020
FAN_TACHOMETERS_OFFSET = 10000

# PSU Constants
PSU_KEY_TEMPLATE = 'PSU_INFO|{}'
PSU_BASE_SUB_ID = 600000000
PSU_POSITION_MULTIPLE = 1000000
PSU_SENSOR_MULTIPLE = 1000
# field_name : (name, position)
PSU_SENSOR_INFO = {
    'temp': ('Temperature', 1),
    'power': ('Power', 2),
    'current': ('Current', 3),
    'voltage': ('Voltage', 4),
}

# Thermal Constants
THERMAL_KEY_TEMPLATE = 'TEMPERATURE_INFO|{}'

# Physical Entity Constants
PHYSICAL_ENTITY_KEY_TEMPLATE = 'PHYSICAL_ENTITY_INFO|{}'

# Transceiver Constants
XCVR_KEY_TEMPLATE = 'TRANSCEIVER_INFO|{}'
XCVR_DOM_KEY_TEMPLATE = 'TRANSCEIVER_DOM_SENSOR|{}'
XCVR_SENSOR_OID_LIST = [1, 2, 11, 21, 31, 41, 12, 22, 32, 42, 13, 23, 33, 43]


@pytest.fixture(scope="module")
def snmp_physical_entity_info(duthost, localhost, creds):
    """
    Module level fixture for getting physical entity information from snmp fact
    :param duthost: DUT host object
    :param localhost: localhost object
    :param creds: Credential for snmp
    :return:
    """
    return get_entity_mib(duthost, localhost, creds)


def get_entity_mib(duthost, localhost, creds):
    """
    Get physical entity information from snmp fact
    :param duthost: DUT host object
    :param localhost: localhost object
    :param creds: Credential for snmp
    :return:
    """
    hostip = duthost.host.options['inventory_manager'].get_host(duthost.hostname).vars['ansible_host']
    snmp_facts = localhost.snmp_facts(host=hostip, version="v2c", community=creds["snmp_rocommunity"])['ansible_facts']
    entity_mib = {}
    for oid, info in snmp_facts['snmp_physical_entities'].items():
        entity_mib[int(oid)] = info
    return entity_mib


def test_fan_drawer_info(duthost, snmp_physical_entity_info):
    """
    Verify fan drawer information in physical entity mib with redis database
    :param duthost: DUT host object
    :param snmp_physical_entity_info: Physical entity information from snmp fact
    :return:
    """
    keys = redis_get_keys(duthost, STATE_DB, FAN_DRAWER_KEY_TEMPLATE.format('*'))
    if not keys:
        pytest.skip('Fan drawer information not exists in DB, skipping this test')
    for key in keys:
        drawer_info = redis_hgetall(duthost, STATE_DB, key)
        name = key.split(TABLE_NAME_SEPARATOR_VBAR)[-1]
        entity_info_key = PHYSICAL_ENTITY_KEY_TEMPLATE.format(name)
        entity_info = redis_hgetall(duthost, STATE_DB, entity_info_key)
        position = int(entity_info['position_in_parent'])
        expect_oid = FAN_DRAWER_BASE_SUB_ID + position * FAN_DRAWER_POSITION_MULTIPLE
        assert expect_oid in snmp_physical_entity_info, 'Cannot find fan drawer {} in physical entity mib'.format(name)

        drawer_snmp_fact = snmp_physical_entity_info[expect_oid]
        assert drawer_snmp_fact['entPhysDescr'] == name
        assert drawer_snmp_fact['entPhysContainedIn'] == CHASSIS_OID
        assert drawer_snmp_fact['entPhysClass'] == PHYSICAL_CLASS_CONTAINER
        assert drawer_snmp_fact['entPhyParentRelPos'] == position
        assert drawer_snmp_fact['entPhysName'] == name
        assert drawer_snmp_fact['entPhysHwVer'] == ''
        assert drawer_snmp_fact['entPhysFwVer'] == ''
        assert drawer_snmp_fact['entPhysSwVer'] == ''
        assert drawer_snmp_fact['entPhysSerialNum'] == '' if is_null_str(drawer_info['serial']) else drawer_info[
            'serial']
        assert drawer_snmp_fact['entPhysMfgName'] == ''
        assert drawer_snmp_fact['entPhysModelName'] == '' if is_null_str(drawer_info['model']) else drawer_info['model']
        assert drawer_snmp_fact['entPhysIsFRU'] == REPLACEABLE if drawer_info[
                                                                      'is_replaceable'] == 'True' else NOT_REPLACEABLE


def test_fan_info(duthost, snmp_physical_entity_info):
    """
    Verify fan information in physical entity mib with redis database
    :param duthost: DUT host object
    :param snmp_physical_entity_info: Physical entity information from snmp fact
    :return:
    """
    keys = redis_get_keys(duthost, STATE_DB, FAN_KEY_TEMPLATE.format('*'))
    if not keys:
        pytest.skip('Fan information not exists in DB, skipping this test')
    for key in keys:
        fan_info = redis_hgetall(duthost, STATE_DB, key)
        name = key.split(TABLE_NAME_SEPARATOR_VBAR)[-1]
        entity_info_key = PHYSICAL_ENTITY_KEY_TEMPLATE.format(name)
        entity_info = redis_hgetall(duthost, STATE_DB, entity_info_key)
        position = int(entity_info['position_in_parent'])
        parent_name = entity_info['parent_name']
        if parent_name == CHASSIS_KEY:
            parent_oid = FAN_DRAWER_BASE_SUB_ID + position * FAN_DRAWER_POSITION_MULTIPLE
        else:
            parent_entity_info = redis_hgetall(duthost, STATE_DB, PHYSICAL_ENTITY_KEY_TEMPLATE.format(parent_name))
            parent_position = int(parent_entity_info['position_in_parent'])
            if 'PSU' in parent_name:
                parent_oid = PSU_BASE_SUB_ID + parent_position * PSU_POSITION_MULTIPLE
            else:
                parent_oid = FAN_DRAWER_BASE_SUB_ID + parent_position * FAN_DRAWER_POSITION_MULTIPLE
        expect_oid = parent_oid + position * FAN_POSITION_MULTIPLE
        assert expect_oid in snmp_physical_entity_info, 'Cannot find fan {} in physical entity mib'.format(name)
        fan_snmp_fact = snmp_physical_entity_info[expect_oid]
        assert fan_snmp_fact['entPhysDescr'] == name
        assert fan_snmp_fact['entPhysContainedIn'] == CHASSIS_OID if parent_name == CHASSIS_KEY else parent_oid
        assert fan_snmp_fact['entPhysClass'] == PHYSICAL_CLASS_FAN
        assert fan_snmp_fact['entPhyParentRelPos'] == position
        assert fan_snmp_fact['entPhysName'] == name
        assert fan_snmp_fact['entPhysHwVer'] == ''
        assert fan_snmp_fact['entPhysFwVer'] == ''
        assert fan_snmp_fact['entPhysSwVer'] == ''
        assert fan_snmp_fact['entPhysSerialNum'] == '' if is_null_str(fan_info['serial']) else fan_info[
            'serial']
        assert fan_snmp_fact['entPhysMfgName'] == ''
        assert fan_snmp_fact['entPhysModelName'] == '' if is_null_str(fan_info['model']) else fan_info['model']
        assert fan_snmp_fact['entPhysIsFRU'] == REPLACEABLE if fan_info[
                                                                   'is_replaceable'] == 'True' else NOT_REPLACEABLE

        if not is_null_str(fan_info['speed']):
            tachometers_oid = expect_oid + FAN_TACHOMETERS_OFFSET
            assert tachometers_oid in snmp_physical_entity_info, 'Cannot find fan tachometers info in physical entity mib'
            tachometers_fact = snmp_physical_entity_info[tachometers_oid]
            assert tachometers_fact['entPhysDescr'] == 'tachometers for {}'.format(name)
            assert tachometers_fact['entPhysContainedIn'] == expect_oid
            assert tachometers_fact['entPhysClass'] == PHYSICAL_CLASS_SENSOR
            assert tachometers_fact['entPhyParentRelPos'] == 1
            assert tachometers_fact['entPhysName'] == 'tachometers for {}'.format(name)
            assert tachometers_fact['entPhysHwVer'] == ''
            assert tachometers_fact['entPhysFwVer'] == ''
            assert tachometers_fact['entPhysSwVer'] == ''
            assert tachometers_fact['entPhysSerialNum'] == ''
            assert tachometers_fact['entPhysMfgName'] == ''
            assert tachometers_fact['entPhysModelName'] == ''
            assert tachometers_fact['entPhysIsFRU'] == NOT_REPLACEABLE


def test_psu_info(duthost, snmp_physical_entity_info):
    """
    Verify PSU information in physical entity mib with redis database
    :param duthost: DUT host object
    :param snmp_physical_entity_info: Physical entity information from snmp fact
    :return:
    """
    keys = redis_get_keys(duthost, STATE_DB, PSU_KEY_TEMPLATE.format('*'))
    if not keys:
        pytest.skip('PSU information not exists in DB, skipping this test')
    for key in keys:
        psu_info = redis_hgetall(duthost, STATE_DB, key)
        name = key.split(TABLE_NAME_SEPARATOR_VBAR)[-1]
        entity_info_key = PHYSICAL_ENTITY_KEY_TEMPLATE.format(name)
        entity_info = redis_hgetall(duthost, STATE_DB, entity_info_key)
        position = int(entity_info['position_in_parent'])
        expect_oid = PSU_BASE_SUB_ID + position * PSU_POSITION_MULTIPLE
        if psu_info['presence'] != 'true':
            assert expect_oid not in snmp_physical_entity_info
            continue

        assert expect_oid in snmp_physical_entity_info, 'Cannot find PSU {} in physical entity mib'.format(name)
        psu_snmp_fact = snmp_physical_entity_info[expect_oid]
        assert psu_snmp_fact['entPhysDescr'] == name
        assert psu_snmp_fact['entPhysContainedIn'] == CHASSIS_OID
        assert psu_snmp_fact['entPhysClass'] == PHYSICAL_CLASS_POWERSUPPLY
        assert psu_snmp_fact['entPhyParentRelPos'] == position
        assert psu_snmp_fact['entPhysName'] == name
        assert psu_snmp_fact['entPhysHwVer'] == ''
        assert psu_snmp_fact['entPhysFwVer'] == ''
        assert psu_snmp_fact['entPhysSwVer'] == ''
        assert psu_snmp_fact['entPhysSerialNum'] == '' if is_null_str(psu_info['serial']) else psu_info[
            'serial']
        assert psu_snmp_fact['entPhysMfgName'] == ''
        assert psu_snmp_fact['entPhysModelName'] == '' if is_null_str(psu_info['model']) else psu_info['model']
        assert psu_snmp_fact['entPhysIsFRU'] == REPLACEABLE if psu_info[
                                                                   'is_replaceable'] == 'True' else NOT_REPLACEABLE

        _check_psu_sensor(name, psu_info, expect_oid, snmp_physical_entity_info)


def _check_psu_sensor(psu_name, psu_info, psu_oid, snmp_physical_entity_info):
    """
    Check PSU sensor information in physical entity mib
    :param psu_name: PSU name
    :param psu_info: PSU information got from db
    :param psu_oid: PSU oid
    :param snmp_physical_entity_info: Physical entity information from snmp fact
    :return:
    """
    for field, sensor_tuple in PSU_SENSOR_INFO.items():
        expect_oid = psu_oid + sensor_tuple[1] * PSU_SENSOR_MULTIPLE
        if is_null_str(psu_info[field]):
            assert expect_oid not in snmp_physical_entity_info
            continue

        assert expect_oid in snmp_physical_entity_info, 'Cannot find PSU sensor {} in physical entity mib'.format(field)
        sensor_snmp_fact = snmp_physical_entity_info[expect_oid]
        assert sensor_snmp_fact['entPhysDescr'] == '{} for {}'.format(sensor_tuple[0], psu_name)
        assert sensor_snmp_fact['entPhysContainedIn'] == psu_oid
        assert sensor_snmp_fact['entPhysClass'] == PHYSICAL_CLASS_SENSOR
        assert sensor_snmp_fact['entPhyParentRelPos'] == sensor_tuple[1]
        assert sensor_snmp_fact['entPhysName'] == '{} for {}'.format(sensor_tuple[0], psu_name)
        assert sensor_snmp_fact['entPhysHwVer'] == ''
        assert sensor_snmp_fact['entPhysFwVer'] == ''
        assert sensor_snmp_fact['entPhysSwVer'] == ''
        assert sensor_snmp_fact['entPhysSerialNum'] == ''
        assert sensor_snmp_fact['entPhysMfgName'] == ''
        assert sensor_snmp_fact['entPhysModelName'] == ''
        assert sensor_snmp_fact['entPhysIsFRU'] == NOT_REPLACEABLE


def test_thermal_info(duthost, snmp_physical_entity_info):
    """
    Verify thermal information in physical entity mib with redis database
    :param duthost: DUT host object
    :param snmp_physical_entity_info: Physical entity information from snmp fact
    :return:
    """
    keys = redis_get_keys(duthost, STATE_DB, THERMAL_KEY_TEMPLATE.format('*'))
    if not keys:
        pytest.skip('Thermal information not exists in DB, skipping this test')
    for key in keys:
        name = key.split(TABLE_NAME_SEPARATOR_VBAR)[-1]
        entity_info_key = PHYSICAL_ENTITY_KEY_TEMPLATE.format(name)
        entity_info = redis_hgetall(duthost, STATE_DB, entity_info_key)
        if not entity_info or entity_info['parent_name'] != CHASSIS_KEY:
            continue
        position = int(entity_info['position_in_parent'])
        expect_oid = CHASSIS_MGMT_OID + CHASSIS_THERMAL_OFFSET + position
        assert expect_oid in snmp_physical_entity_info, 'Cannot find thermal {} in physical entity mib'.format(name)
        thermal_snmp_fact = snmp_physical_entity_info[expect_oid]
        assert thermal_snmp_fact['entPhysDescr'] == name
        assert thermal_snmp_fact['entPhysContainedIn'] == CHASSIS_MGMT_OID
        assert thermal_snmp_fact['entPhysClass'] == PHYSICAL_CLASS_SENSOR
        assert thermal_snmp_fact['entPhyParentRelPos'] == position
        assert thermal_snmp_fact['entPhysName'] == name
        assert thermal_snmp_fact['entPhysHwVer'] == ''
        assert thermal_snmp_fact['entPhysFwVer'] == ''
        assert thermal_snmp_fact['entPhysSwVer'] == ''
        assert thermal_snmp_fact['entPhysSerialNum'] == ''
        assert thermal_snmp_fact['entPhysMfgName'] == ''
        assert thermal_snmp_fact['entPhysModelName'] == ''
        assert thermal_snmp_fact['entPhysIsFRU'] == NOT_REPLACEABLE


def test_transceiver_info(duthost, snmp_physical_entity_info):
    """
    Verify transceiver information in physical entity mib with redis database
    :param duthost: DUT host object
    :param snmp_physical_entity_info: Physical entity information from snmp fact
    :return:
    """
    keys = redis_get_keys(duthost, STATE_DB, XCVR_KEY_TEMPLATE.format('*'))
    if not keys:
        pytest.skip('Transceiver information not exists in DB, skipping this test')

    name_to_snmp_facts = {}
    for oid, values in snmp_physical_entity_info.items():
        values['oid'] = oid
        name_to_snmp_facts[values['entPhysName']] = values
    for key in keys:
        name = key.split(TABLE_NAME_SEPARATOR_VBAR)[-1]
        assert name in name_to_snmp_facts, 'Cannot find port {} in physical entity mib'.format(name)
        transceiver_info = redis_hgetall(duthost, STATE_DB, key)
        transceiver_snmp_fact = name_to_snmp_facts[name]
        assert transceiver_snmp_fact['entPhysDescr'] is not None
        assert transceiver_snmp_fact['entPhysContainedIn'] == CHASSIS_OID
        assert transceiver_snmp_fact['entPhysClass'] == PHYSICAL_CLASS_PORT
        assert transceiver_snmp_fact['entPhyParentRelPos'] == -1
        assert transceiver_snmp_fact['entPhysName'] == name
        assert transceiver_snmp_fact['entPhysHwVer'] == transceiver_info['hardware_rev']
        assert transceiver_snmp_fact['entPhysFwVer'] == ''
        assert transceiver_snmp_fact['entPhysSwVer'] == ''
        assert transceiver_snmp_fact['entPhysSerialNum'] == transceiver_info['serial']
        assert transceiver_snmp_fact['entPhysMfgName'] == transceiver_info['manufacturer']
        assert transceiver_snmp_fact['entPhysModelName'] == transceiver_info['model']
        assert transceiver_snmp_fact['entPhysIsFRU'] == REPLACEABLE if transceiver_info[
                                                                           'is_replaceable'] == 'True' else NOT_REPLACEABLE
        _check_transceiver_dom_sensor_info(transceiver_snmp_fact['oid'], snmp_physical_entity_info)


def _check_transceiver_dom_sensor_info(transceiver_oid, snmp_physical_entity_info):
    """
    Check transceiver DOM sensor information in physical entity mib
    :param transceiver_oid: Transceiver oid
    :param snmp_physical_entity_info: Physical entity information from snmp fact
    :return:
    """
    for index, sensor_oid_offset in enumerate(XCVR_SENSOR_OID_LIST):
        expect_oid = transceiver_oid + sensor_oid_offset
        assert expect_oid in snmp_physical_entity_info, 'Cannot find port sensor in physical entity mib'
        sensor_snmp_fact = snmp_physical_entity_info[expect_oid]
        assert sensor_snmp_fact['entPhysDescr'] is not None
        assert sensor_snmp_fact['entPhysContainedIn'] == transceiver_oid
        assert sensor_snmp_fact['entPhysClass'] == PHYSICAL_CLASS_SENSOR
        assert sensor_snmp_fact['entPhyParentRelPos'] == index + 1
        assert sensor_snmp_fact['entPhysName'] is not None
        assert sensor_snmp_fact['entPhysHwVer'] == ''
        assert sensor_snmp_fact['entPhysFwVer'] == ''
        assert sensor_snmp_fact['entPhysSwVer'] == ''
        assert sensor_snmp_fact['entPhysSerialNum'] == ''
        assert sensor_snmp_fact['entPhysMfgName'] == ''
        assert sensor_snmp_fact['entPhysModelName'] == ''
        assert sensor_snmp_fact['entPhysIsFRU'] == NOT_REPLACEABLE


@pytest.mark.disable_loganalyzer
def test_turn_off_psu_and_check_psu_info(duthost, localhost, creds, psu_controller):
    """
    Turn off one PSU and check all PSU sensor entity being removed because it can no longer get any value
    :param duthost: DUT host object
    :param localhost: localhost object
    :param creds: Credential for snmp
    :param psu_controller: PSU controller
    :return:
    """
    psu_status = psu_controller.get_psu_status()
    if len(psu_status) < 2:
        pytest.skip('At least 2 PSUs required for rest of the testing in this case')

    # turn on all PSU
    for item in psu_status:
        if not item['psu_on']:
            psu_controller.turn_on_psu(item["psu_id"])
            time.sleep(5)

    psu_status = psu_controller.get_psu_status()
    for item in psu_status:
        if not item['psu_on']:
            pytest.skip('Not all PSU are powered on, skip rest of the testing in this case')

    # turn off the first PSU
    first_psu_id = psu_status[0]['psu_id']
    psu_controller.turn_off_psu(first_psu_id)
    assert wait_until(30, 5, check_psu_status, psu_controller, first_psu_id, False)
    # wait for psud update the database
    assert wait_until(120, 20, _check_psu_status_after_power_off, duthost, localhost, creds)


def _check_psu_status_after_power_off(duthost, localhost, creds):
    """
    Check that at least one PSU is powered off and its sensor information should be removed from mib
    :param duthost: DUT host object
    :param localhost: localhost object
    :param creds: Credential for snmp
    :return: True if sensor information is removed from mib
    """
    mib_info = get_entity_mib(duthost, localhost, creds)
    keys = redis_get_keys(duthost, STATE_DB, PSU_KEY_TEMPLATE.format('*'))
    power_off_psu_found = False
    for key in keys:
        psu_info = redis_hgetall(duthost, STATE_DB, key)
        name = key.split(TABLE_NAME_SEPARATOR_VBAR)[-1]
        entity_info_key = PHYSICAL_ENTITY_KEY_TEMPLATE.format(name)
        entity_info = redis_hgetall(duthost, STATE_DB, entity_info_key)
        position = int(entity_info['position_in_parent'])
        expect_oid = PSU_BASE_SUB_ID + position * PSU_POSITION_MULTIPLE
        if psu_info['status'] != 'true':
            assert expect_oid in mib_info
            for field, sensor_tuple in PSU_SENSOR_INFO.items():
                sensor_oid = expect_oid + sensor_tuple[1] * PSU_SENSOR_MULTIPLE
                if sensor_oid not in mib_info:
                    power_off_psu_found = True
                    break
    return power_off_psu_found


def redis_get_keys(duthost, db_id, pattern):
    """
    Get all keys for a given pattern in given redis database
    :param duthost: DUT host object
    :param db_id: ID of redis database
    :param pattern: Redis key pattern
    :return: A list of key name in string
    """
    cmd = 'redis-cli --raw -n {} KEYS \"{}\"'.format(db_id, pattern)
    logging.debug('Getting keys from redis by command: {}'.format(cmd))
    output = duthost.shell(cmd)
    content = output['stdout'].strip()
    return content.split('\n') if content else None


def redis_hgetall(duthost, db_id, key):
    """
    Get all field name and values for a given key in given redis dataabse
    :param duthost: DUT host object
    :param db_id: ID of redis database
    :param key: Redis Key
    :return: A dictionary, key is field name, value is field value
    """
    cmd = 'redis-cli --raw -n {} HGETALL \"{}\"'.format(db_id, key)
    logging.debug('HGETALL from redis by command: {}'.format(cmd))
    output = duthost.shell(cmd)
    content = output['stdout'].strip()
    result = {}
    if content:
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            result[lines[i]] = lines[i + 1]
            i += 2
    return result


def is_null_str(value):
    """
    Indicate if a string is None or 'None' or 'N/A'
    :param value: A string value
    :return: True if a string is None or 'None' or 'N/A'
    """
    return not value or value == str(None) or value == 'N/A'


def check_psu_status(psu_controller, psu_id, expect_status):
    """
    Check if a given PSU is at expect status
    :param psu_controller: PSU controller
    :param psu_id: PSU id
    :param expect_status: Expect bool status, True means on, False means off
    :return: True if a given PSU is at expect status
    """
    status = psu_controller.get_psu_status(psu_id)
    return 'psu_on' in status[0] and status[0]['psu_on'] == expect_status
