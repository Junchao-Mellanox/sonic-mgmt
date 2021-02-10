from tests.common.helpers.assertions import pytest_require
from tests.common.helpers.dut_ports import decode_dut_port_name
from tests.platform_tests.link_flap.link_flap_utils import build_test_candidates


STATE_DB = 'STATE_DB'
STATE_PORT_TABLE_TEMPLATE = 'PORT_TABLE|{}'
STATE_PORT_FIELD_SUPPORTED_SPEEDS = 'supported_speeds'


def get_sonic_port_supported_speeds(duthost, port_name):
    supported_speeds = redis_hget(duthost, 
                                  STATE_DB, 
                                  STATE_PORT_TABLE_TEMPLATE.format(port_name),
                                  STATE_PORT_FIELD_SUPPORTED_SPEEDS)
    return None if not supported_speeds else supported_speeds.split(',')



def get_onyx_port_supported_speeds(fanout, port_name):
    supported_speeds_line = fanout.command('show interfaces {} capabilities | include Speed'.format(port_name))
    items = supported_speeds_line.split(':')
    if len(items) != 2:
        return None

    return [speed for speed in items[1].strip().split(',') if speed != 'auto']



def redis_hget(duthost, db_id, key, field):
    """
    Get field value for a given key in given redis dataabse
    :param duthost: DUT host object
    :param db_id: ID of redis database
    :param key: Redis Key
    :param field: Field name
    :return: A dictionary, key is field name, value is field value
    """
    cmd = 'sonic-db-cli {} HGET \"{}\" \"{}\"'.format(db_id, key, field)
    output = duthost.shell(cmd)
    return output['stdout'].strip()
    

def test_auto_negotiation(request, duthosts, enum_dut_portname, fanouthosts):
    dutname, portname = decode_dut_port_name(enum_dut_portname)
    for dut in duthosts:
        if dutname == 'unknown' or dutname == dut.hostname:
            run_auto_negotiation_test(dut, fanouthosts, portname)


def run_auto_negotiation_test(dut, fanouthosts, portname):
    candidates = build_test_candidates(dut, fanouthosts, portname)
    pytest_require(candidates, "Didn't find any port that is admin up and present in the connection graph")
    for dut_port, fanout, fanout_port in candidates:
        sonic_supported_speeds = get_sonic_port_supported_speeds(dut, dut_port)
        if not sonic_supported_speeds:
            continue

        onyx_supported_speeds = get_onyx_port_supported_speeds(fanout, fanout_port)
        if not onyx_supported_speeds:
            continue

        for onyx_speed in onyx_supported_speeds:
            expect_sonic_speed = onyx_speed[:-1] + '000'
            if expect_sonic_speed not in sonic_supported_speeds:
                continue

            dut.shell('config interface autoneg {} enabled'.format(dut_port))
            fanout.shutdown(fanout_port)
            fanout.set_interface_speed(fanout_port, onyx_speed)
            fanout.no_shutdown(fanout_port)

            dut.shell('config interface advertised-speeds {} {}'.format(dut_port, expect_sonic_speed))





