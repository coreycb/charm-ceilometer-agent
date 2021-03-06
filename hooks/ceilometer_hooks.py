#!/usr/bin/python
#
# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import sys
import json
from charmhelpers.fetch import (
    apt_install, filter_installed_packages,
    apt_update
)
from charmhelpers.core.hookenv import (
    config,
    Hooks, UnregisteredHookError,
    log,
    is_relation_made,
    relation_set,
    status_set,
)
from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    openstack_upgrade_available,
    pausable_restart_on_change as restart_on_change,
)
from ceilometer_utils import (
    restart_map,
    services,
    register_configs,
    CEILOMETER_AGENT_PACKAGES,
    NOVA_SETTINGS,
    do_openstack_upgrade,
    assess_status,
)
from charmhelpers.contrib.charmsupport import nrpe

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook()
def install():
    origin = config('openstack-origin')
    configure_installation_source(origin)
    status_set('maintenance', 'Installing apt packages')
    apt_update(fatal=True)
    apt_install(
        filter_installed_packages(CEILOMETER_AGENT_PACKAGES),
        fatal=True)


@hooks.hook('nova-ceilometer-relation-joined')
def nova_ceilometer_joined():
    relation_set(subordinate_configuration=json.dumps(NOVA_SETTINGS))


@hooks.hook("ceilometer-service-relation-changed",
            "upgrade-charm")
@restart_on_change(restart_map())
def ceilometer_changed():
    CONFIGS.write_all()
    if is_relation_made('nrpe-external-master'):
        update_nrpe_config()


@hooks.hook('config-changed')
@restart_on_change(restart_map(), stopstart=True)
def config_changed():
    if not config('action-managed-upgrade'):
        if openstack_upgrade_available('ceilometer-common'):
            status_set('maintenance', 'Running openstack upgrade')
            do_openstack_upgrade(CONFIGS)
    if is_relation_made('nrpe-external-master'):
        update_nrpe_config()
    CONFIGS.write_all()


@hooks.hook('nrpe-external-master-relation-joined',
            'nrpe-external-master-relation-changed')
def update_nrpe_config():
    # python-dbus is used by check_upstart_job
    apt_install('python-dbus')
    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname)
    nrpe.add_init_service_checks(nrpe_setup, services(), current_unit)
    nrpe_setup.write()


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
    # set_os_workload_status(CONFIGS, REQUIRED_INTERFACES)
    assess_status(CONFIGS)
