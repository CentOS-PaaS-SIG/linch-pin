#!/usr/bin/env python

import os
import ast
import json
import time
import hashlib

from cerberus import Validator
from uuid import getnode as get_mac

from linchpin.ansible_runner import ansible_runner

from linchpin.hooks.state import State
# from linchpin.hooks import LinchpinHooks

from linchpin.rundb.basedb import BaseDB
from linchpin.rundb.drivers import DB_DRIVERS

from linchpin.exceptions import LinchpinError
from linchpin.exceptions import SchemaError


class LinchpinAPI(object):

    def __init__(self, ctx):
        """
        LinchpinAPI constructor

        :param ctx: context object from context.py

        """

        self.ctx = ctx
        self.set_evar('from_api', True)

#        self.hook_state = None
#        self._hook_observers = []
#        self.playbook_pre_states = self.get_cfg('playbook_pre_states',
#                                                {'up': 'preup',
#                                                 'destroy': 'predestroy'})
#        self.playbook_post_states = self.get_cfg('playbook_post_states',
#                                                 {'up': 'postup',
#                                                  'destroy': 'postdestroy',
#                                                  'postinv': 'inventory'})
#        self.hooks = LinchpinHooks(self)
#
#        self.target_data = {}

        base_path = '/'.join(os.path.dirname(__file__).split('/')[0:-1])
        pkg = self.get_cfg(section='lp', key='pkg', default='linchpin')
        lp_path = '{0}/{1}'.format(base_path, pkg)
        self.pb_ext = self.get_cfg('playbooks', 'extension', default='.yml')

        # get external_provider_path
        xp_path = self.get_cfg('lp',
                               'external_providers_path',
                               default='').split(':')

        pb_path = '{0}/{1}'.format(lp_path,
                                   self.get_evar('playbooks_folder',
                                                 default='provision'))
        self.pb_path = [pb_path]

        for path in xp_path:
            self.pb_path.append(os.path.expanduser(path))

        self.set_evar('lp_path', lp_path)
        self.set_evar('pb_path', self.pb_path)


    def setup_rundb(self):
        """
        Configures the run database parameters, sets them into extra_vars
        """

        rundb_conn_default = '~/.config/linchpin/rundb-::mac::.json'
        rundb_conn = self.get_cfg(section='lp',
                                  key='rundb_conn',
                                  default=rundb_conn_default)
        rundb_type = self.get_cfg(section='lp',
                                  key='rundb_type',
                                  default='TinyRunDB')
        rundb_conn_type = self.get_cfg(section='lp',
                                       key='rundb_conn_type',
                                       default='file')
        self.rundb_hash = self.get_cfg(section='lp',
                                       key='rundb_hash',
                                       default='sha256')

        if rundb_conn_type == 'file':
            rundb_conn_int = rundb_conn.replace('::mac::', str(get_mac()))
            rundb_conn_int = os.path.expanduser(rundb_conn_int)
            rundb_conn_dir = os.path.dirname(rundb_conn_int)

            if not os.path.exists(rundb_conn_dir):
                os.mkdir(rundb_conn_dir)


        self.set_evar('rundb_type', rundb_type)
        self.set_evar('rundb_conn', rundb_conn_int)
        self.set_evar('rundb_hash', self.rundb_hash)


        return BaseDB(DB_DRIVERS[rundb_type], rundb_conn_int)


    def get_cfg(self, section=None, key=None, default=None):
        """
        Get cfgs value(s) by section and/or key, or the whole cfgs object

        :param section: section from ini-style config file

        :param key: key to get from config file, within section

        :param default: default value to return if nothing is found.

        Does not apply if section is not provided.
        """

        return self.ctx.get_cfg(section=section, key=key, default=default)


    def set_cfg(self, section, key, value):
        """
        Set a value in cfgs. Does not persist into a file,
        only during the current execution.


        :param section: section within ini-style config file

        :param key: key to use

        :param value: value to set into section within config file
        """

        self.ctx.set_cfg(section, key, value)


    def get_evar(self, key=None, default=None):
        """
        Get the current evars (extra_vars)

        :param key: key to use

        :param default: default value to return if nothing is found
        (default: None)
        """

        return self.ctx.get_evar(key=key, default=default)


    def set_evar(self, key, value):
        """
        Set a value into evars (extra_vars). Does not persist into a file,
        only during the current execution.

        :param key: key to use

        :param value: value to set into evars
        """

        self.ctx.set_evar(key, value)


    @property
    def hook_state(self):
        """
        getter function for hook_state property of the API object
        """

        return self.hook_state


    @hook_state.setter
    def hook_state(self, hook_state):
        """
        hook_state property setter , splits the hook_state string in
        subhook_state and sets linchpin.hook_state object

        :param hook_state: valid hook_state string mentioned in linchpin.conf
        """

        # call run_hooks after hook_state is being set
        if hook_state is None:
            return
        else:
            self.ctx.log_debug('hook {0} initiated'.format(hook_state))
            self._hook_state = State(hook_state, None, self.ctx)

            for callback in self._hook_observers:
                callback(self._hook_state)


    def bind_to_hook_state(self, callback):
        """
        Function used by LinchpinHooksclass to add callbacks

        :param callback: callback function
        """

        self._hook_observers.append(callback)


    def lp_journal(self, targets=[], fields=None, count=None):

        rundb = self.setup_rundb()

        journal = {}

        if not len(targets):
            targets = rundb.get_tables()


        for target in targets:
            journal[target] = rundb.get_records(table=target, count=count)

        return journal


    def _find_playbook_path(self, playbook):

        for path in self.pb_path:
            p = '{0}/{1}{2}'.format(path, playbook, self.pb_ext)

            if os.path.exists(os.path.expanduser(p)):
                return path

        raise LinchpinError("playbook '{0}' not found in"
                            " path: {1}".format(playbook, self.pb_path))


    def _validate_topology(self, topology):
        """
        Validate the provided topology against the schema

        ;param topology: topology dictionary
        """

        res_grps = topology.get('resource_groups')
        resources = []

        for group in res_grps:
            res_grp_type = (group.get('resource_group_type') or
                            group.get('res_group_type'))

            pb_path = self._find_playbook_path(res_grp_type)

            try:
                schema_path = "{0}/roles/{1}/files/schema.json".format(pb_path,
                                                                       res_grp_type)

                schema = json.load(open(schema_path))
            except Exception as e:
                raise LinchpinError("Error with schema: '{0}'"
                                    " {1}".format(schema_path, e))

            res_defs = group.get('resource_definitions')

            # preload this so it will validate against the schema
            document = {'res_defs': res_defs}
            v = Validator(schema)

            if not v.validate(document):
                raise SchemaError('Schema validation failed:'
                                  ' {0}'.format(v.errors))

            resources.append(group)

        return resources


    def do_action(self, provision_data, action='up', run_id=None):
        """
        This function takes a list of targets, and executes the given
        action (up, destroy, etc.) for each provided target.

        :param pinfile_datra: PinFile as a dictionary, with target information

        :param targets: A tuple of targets to run. (Default: [])

        .. .note:: The `run_id` value differs from the `rundb_id`, in that
                   the `run_id` is an existing value in the database.
                   The `rundb_id` value is created to store the new record.
                   If the `run_id` is passed, it is used to collect an existing
                   `uhash` value from the given `run_id`, which is in turn used
                   to perform an idempotent reprovision, or destroy provisioned
                   resources.
        """

        # playbooks check whether from_cli is defined
        # if not, vars get loaded from linchpin.conf
        self.set_evar('from_api', True)

        ansible_console = False
        if self.ctx.cfgs.get('ansible'):
            ansible_console = (
                ast.literal_eval(self.get_cfg('ansible',
                                              'console',
                                              default='False')))

        if not ansible_console:
            ansible_console = self.ctx.verbose


        self.set_evar('_action', action)

        self.set_evar('state', 'present')

        if action == 'destroy':
            self.set_evar('state', 'absent')

        results = {}

        # initialize rundb table
        dateformat = self.get_cfg('logger',
                                  'dateformat',
                                  default='%m/%d/%Y %I:%M:%S %p')

#        # add this because of magic_var evaluation in ansible
#        self.set_evar('inventory_dir', self.get_evar(
#                      'default_inventories_path',
#                      default='inventories'))

        for target in provision_data.keys():

            results[target] = {}
            self.set_evar('target', target)

            rundb = self.setup_rundb()
            rundb_schema = json.loads(self.get_cfg(section='lp',
                                      key='rundb_schema'))
            rundb.schema = rundb_schema
            self.set_evar('rundb_schema', rundb_schema)

            start = time.strftime(dateformat)
            uhash = None

            # generate a new rundb_id
            # (don't confuse it with an already existing run_id)
            rundb_id = rundb.init_table(target)

            if action == 'up' and not run_id:
                uh = hashlib.new(self.rundb_hash,
                                 ':'.join([target, str(rundb_id), start]))
                uhash = uh.hexdigest()[-4:]
            elif action == 'destroy' or run_id:
                # look for the action='up' records to destroy
                data, orig_run_id = rundb.get_record(target,
                                                     action='up',
                                                     run_id=run_id)

                if data:
                    self.set_evar('orig_run_id', orig_run_id)
                    uhash = data.get('uhash')
                    self.ctx.log_debug("using data from"
                                       " run_id: {0}".format(run_id))
                else:
                    raise LinchpinError("Attempting to perform '{0}' action on"
                                        " target: '{1}' failed. No records"
                                        " available.".format(action, target))
            else:
                raise LinchpinError("run_id '{0}' does not match any existing"
                                    " records".format(run_id))


            self.ctx.log_debug('rundb_id: {0}'.format(rundb_id))
            self.ctx.log_debug('uhash: {0}'.format(uhash))

            rundb.update_record(target, rundb_id, 'uhash', uhash)
            rundb.update_record(target, rundb_id, 'start', start)
            rundb.update_record(target, rundb_id, 'action', action)

            self.set_evar('rundb_id', rundb_id)
            self.set_evar('uhash', uhash)

            topology_data = provision_data[target]['topology']
            resources = self._validate_topology(topology_data)
            self.set_evar('topo_data', topology_data)
            self.set_evar('resources', resources)

            rundb.update_record(target,
                                rundb_id,
                                'inputs',
                                [
                                    {'topology_data':
                                     provision_data[target]['topology']}
                                ])



            if provision_data[target].get('layout', None):
                self.set_evar('layout_data', provision_data[target]['layout'])

                rundb.update_record(target,
                                    rundb_id,
                                    'inputs',
                                    [
                                        {'layout_data':
                                         provision_data[target]['layout']}
                                    ])

        # set inventory_file

        # set the current target data
        # this will differ with dynamic inputs
#        self.target_data = pf[target]
#        self.target_data["extra_vars"] = self.get_evar()

        # note : changing the state triggers the hooks
#        self.hooks.rundb = (rundb, rundb_id)
#        self.pb_hooks = self.get_cfg('hookstates', action)
            self.ctx.log_debug('calling: {0}{1}'.format('pre', action))

#        if 'pre' in self.pb_hooks:
#            self.hook_state = '{0}{1}'.format('pre', action)

        # FIXME need to add rundb data for hooks results

        # invoke the appropriate action
            return_code, results[target]['task_results'] = (
                self._invoke_playbooks(resources, action=action,
                                       console=ansible_console)
            )

            if not return_code:
                self.ctx.log_state("Action '{0}' on Target '{1}' is "
                                   "complete".format(action, target))

        # FIXME Check the result[target] value here, and fail if applicable.
        # It's possible that a flag might allow more targets to run, then
        # return an error code at the end.

        # add post provision hook for inventory generation
#        if 'inv' in self.pb_hooks:
#            self.hook_state = 'postinv'
#
#        if 'post' in self.pb_hooks:
#            self.hook_state = '{0}{1}'.format('post', action)

            end = time.strftime(dateformat)
            rundb.update_record(target, rundb_id, 'end', end)
            rundb.update_record(target, rundb_id, 'rc', return_code)

            if action == 'destroy':
                run_data = rundb.get_record(target,
                                            action=action,
                                            run_id=orig_run_id)
            else:
                run_data = rundb.get_record(target,
                                            action=action,
                                            run_id=rundb_id)

            results[target]['rundb_data'] = {rundb_id: run_data[0]}

        return (return_code, results)


    def _invoke_playbooks(self, resources, action='up', console=True):
        """
        Uses the Ansible API code to invoke the specified linchpin playbook

        :param action: Which ansible action to run (default: 'up')
        :param console: Whether to display the ansible console (default: True)
        """

        return_code = 0
        results = []

        for resource in resources:
            playbook = resource.get('resource_group_type')
            pb_path = self._find_playbook_path(playbook)
            playbook_path = '{0}/{1}{2}'.format(pb_path, playbook, self.pb_ext)

            module_paths = []
            module_folder = self.get_cfg('lp', 'module_folder', default='library')

            for path in reversed(self.pb_path):
               module_paths.append('{0}/{1}/'.format(path, module_folder))

            extra_var = self.get_evar()

            return_code, res = ansible_runner(playbook_path,
                                              module_paths,
                                              extra_var,
                                              console=console)

            if res:
                results.append(res)


        if not len(results):
            results = None

        return (return_code, results)
