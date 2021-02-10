<<<<<<< HEAD
"""
Tool used for shutdown/startup port on the DUT.
"""

import datetime
import os
import jinja2
=======
"""Utility for shutting down/bringing up ports on the DUT."""
>>>>>>> master
import time
import logging
import pprint

from tests.common.helpers.assertions import pytest_assert
from tests.common.utilities import wait_until

logger = logging.getLogger(__name__)

<<<<<<< HEAD
BASE_DIR = os.path.dirname(os.path.realpath(__file__))
DUT_TMP_DIR = '/tmp/port_toggle'
TEMPLATE_DIR = os.path.join(BASE_DIR, 'templates')
PORT_TOGGLE_TEMPLATE = 'port_toggle.j2'
=======
BASE_PORT_COUNT = 28.0  # default t0 topology has 28 ports to toggle
>>>>>>> master


def port_toggle(duthost, tbinfo, ports=None, wait_time_getter=None, wait_after_ports_up=60, watch=False):
    """Toggle ports on the DUT.

    Args:
        duthost: DUT host object
        tbinfo: Information about the testbed
        ports: Specify list of ports, None if toggle all ports
        wait_time_getter: A call back function to get port toggle wait time.
        wait_after_ports_up: Time to wait after interfaces become up
        watch: Logging system state
    """
    def __get_down_ports(expect_up=True):
        """Check interface status and return the down ports in a set."""
        ports_down = duthost.interface_facts(up_ports=ports)["ansible_facts"]["ansible_interface_link_down_ports"]
        db_ports_down = duthost.show_interface(command="status", up_ports=ports)["ansible_facts"]\
            ["ansible_interface_link_down_ports"]
        if expect_up:
            return set(ports_down) | set(db_ports_down)
        else:
            return set(ports_down) & set(db_ports_down)

    if not ports:
        logger.info("No ports specified, toggling all minigraph ports")
        mg_facts = duthost.get_extended_minigraph_facts(tbinfo)
        ports = mg_facts["minigraph_ports"].keys()

    if not wait_time_getter:
        wait_time_getter = default_port_toggle_wait_time

    port_down_wait_time, port_up_wait_time = wait_time_getter(duthost, len(ports))
    logger.info("Toggling ports:\n%s", pprint.pformat(ports))

    shutdown_ok = False
    shutdown_err_msg = ""
    try:
        config_ports_admin_status(duthost, ports, 'down')
        if watch:
            time.sleep(1)
            log_system_resources(duthost, logger)

        logger.info("Wait for ports to go down")
        shutdown_ok = wait_until(port_down_wait_time, 5, lambda: len(__get_down_ports(expect_up=False)) == len(ports))

        if not shutdown_ok:
            up_ports = __get_down_ports(expect_up=True)
            shutdown_err_msg = "Some ports did not go down as expected: {}".format(str(up_ports))
    except Exception as e:
        shutdown_err_msg = "Shutdown ports failed with exception: {}".format(repr(e))

    startup_ok = False
    startup_err_msg = ""
    try:
        config_ports_admin_status(duthost, ports, 'up')

        logger.info("Wait for ports to come up")
        startup_ok = wait_until(port_up_wait_time, 5, lambda: len(__get_down_ports()) == 0)

        if not startup_ok:
            down_ports = __get_down_ports()
            startup_err_msg = "Some ports did not come up as expected: {}".format(str(down_ports))
    except Exception as e:
        startup_err_msg = "Startup ports failed with exception: {}".format(repr(e))

    pytest_assert(shutdown_ok, shutdown_err_msg)
    pytest_assert(startup_ok, startup_err_msg)

    logger.info("Wait %d seconds for system to stabilize", wait_after_ports_up)
    time.sleep(wait_after_ports_up)


def log_system_resources(duthost, logger):
    # Watch memory status
    memory_output = duthost.shell("show system-memory")["stdout"]
    logger.info("Memory Status: %s", memory_output)

    # Watch orchagent CPU utilization
    orch_cpu = duthost.shell("show processes cpu | grep orchagent | awk '{print $9}'")["stdout"]
    logger.info("Orchagent CPU Util: %s", orch_cpu)

    # Watch Redis Memory
    redis_memory = duthost.shell("redis-cli info memory | grep used_memory_human")["stdout"]
    logger.info("Redis Memory: %s", redis_memory)


def default_port_toggle_wait_time(duthost, port_count):
    """Get the default timeout for shutting down/starting up a set of ports.

    Port toggle wait time can depend on many factors: port count, cpu type, etc. The callback allows
    users to customize port toggle wait behavior based on DUT specs and port count.

    Args:
        duthost: DUT host object
        port_count: total number of ports to toggle

    Returns
        (int, int): timeout for shutting down ports, and timeout for bringing up ports
    """
    port_down_wait_time, port_up_wait_time = 120, 180
    asic_type = duthost.facts["asic_type"]

    if asic_type == "mellanox":
        if port_count <= BASE_PORT_COUNT:
            port_count = BASE_PORT_COUNT

        port_count_factor = port_count / BASE_PORT_COUNT
        port_down_wait_time = int(port_down_wait_time * port_count_factor)
        port_up_wait_time = int(port_up_wait_time * port_count_factor)

    return port_down_wait_time, port_up_wait_time


def config_ports_admin_status(duthost, ports, status):
    """Config ports admin status

    Args:
        duthost: DUT host object
        ports: Port name list
        status: Port status
    """
    port_toggle_vars = {
        'port_names': ports,
        'port_status': status
    }

    ports_config_path = os.path.join(DUT_TMP_DIR, 'config_port_{}.json'.format(status))
    config_template = jinja2.Template(open(os.path.join(TEMPLATE_DIR, PORT_TOGGLE_TEMPLATE)).read())

    duthost.command("mkdir -p {}".format(DUT_TMP_DIR))
    duthost.copy(content=config_template.render(port_toggle_vars), dest=ports_config_path)
    duthost.command('sonic-cfggen -j {} --write-to-db'.format(ports_config_path))
