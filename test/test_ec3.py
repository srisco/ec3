# test_radl - Test for module ``radl``.
# Copyright (C) 2014 - GRyCAP - Universitat Politecnica de Valencia
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
import unittest
import logging
from mock import patch, MagicMock, mock_open
from collections import namedtuple
try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO
try:
    from urlparse import urlparse
except ImportError:
    from urllib.parse import urlparse

sys.path.append("..")
sys.path.append(".")

from IM2.radl.radl import RADL, system, network
from ec3 import ClusterStore, CLI, CmdLaunch, CmdList, CmdTemplates, CmdDestroy

cluster_data = """system front (
                    state = 'configured' and
                    __im_server = 'http://server.com:8800' and
                    __infrastructure_id = 'infid' and
                    __vm_id = '0' and
                    auth = '[{"type": "InfrastructureManager", "username": "user", "password": "pass"}]'
                    )"""

if sys.version_info > (3, 0):
    open_name = 'builtins.open'
else:
    open_name = '__builtin__.open'

class TestEC3(unittest.TestCase):

    def __init__(self, *args):
        unittest.TestCase.__init__(self, *args)

    def get_response(self, method, url, verify, headers, data=None):
        resp = MagicMock()
        resp.status_code = 400
        parts = urlparse(url)
        url = parts[2]
        params = parts[4]

        if method == "GET":
            if url == "/infrastructures/infid" or url == "/infrastructures/newinfid":
                resp.status_code = 200
                resp.json.return_value = {"uri-list": [{ "uri": "http://server.com/infid/vms/0"},
                                                       { "uri": "http://server.com/infid/vms/1"}]}
            elif url == "/infrastructures/infid/state":
                resp.status_code = 200
                resp.json.return_value = {"state": {"state": "configured",
                                                    "vm_states": {"0": "configured",
                                                                  "1": "configured"}}}
            elif url == "/infrastructures/infid/vms/0":
                resp.status_code = 200
                resp.text = "network public (outbound='yes')\n"
                resp.text += "system front (net_interface.0.connection = 'public' and net_interface.0.ip = '8.8.8.8')"
            elif url == "/infrastructures/infid/data":
                resp.status_code = 200
                resp.json.return_value = {"data": "data"}
            elif url == "/infrastructures/infid/contmsg":
                resp.status_code = 200
                resp.text = "contmsg"
        elif method == "POST":
            if url == "/infrastructures":
                resp.status_code = 200
                resp.text = 'http://server.com/infid'
        elif method == "PUT":
            if url == "/infrastructures":
                resp.status_code = 200
                resp.text = 'http://server.com/newinfid'
        elif method == "DELETE":
            if url == "/infrastructures/infid":
                resp.status_code = 200

        return resp

    @patch('ec3.ClusterStore')
    def test_list(self, cluster_store):
        cluster_store.list.return_value = ["name"]
        radl = RADL()
        n = network("public")
        n.setValue("outbound", "yes")
        s = system("front")
        s.setValue("ec3aas.username", "user")
        s.setValue("state", "configured")
        s.setValue("nodes", "1")
        s.setValue("net_interface.0.connection", n)
        s.setValue("net_interface.0.ip", "8.8.8.8")
        radl.add(s)
        cluster_store.load.return_value = radl
        Options = namedtuple('Options', ['json', 'refresh', 'username'])
        options = Options(json=False, refresh=False, username=['user'])
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        CmdList.run(options)
        res = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertEquals(res, " name    state       IP     nodes \n----------------------------------\n name  configured  8.8.8.8    1   \n")

    @patch('ec3.ClusterStore')
    @patch('ec3.CLI.display')
    @patch('requests.request')
    def test_launch(self, requests, display, cluster_store):
        Options = namedtuple('Options', ['quiet'])
        cli_options = Options(quiet=False)
        CLI.logger = logging.getLogger('ec3')
        CLI.options = cli_options
        cluster_store.list.return_value = ["name"]
        Options = namedtuple('Options', ['not_store', 'clustername', 'auth_file', 'restapi', 'dry_run', 'templates',
                                         'add', 'golden_image', 'print_radl', 'json', 'yes', 'destroy'])
        auth_file = [MagicMock()]
        auth_file[0].readlines.return_value = ["type = InfrastructureManager; username = user; password = pass"]
        options = Options(not_store=False, clustername="name", auth_file=auth_file, restapi=['http://server.com:8800'],
                          dry_run=True, templates=['ubuntu-ec2','kubernetes'], add=False, golden_image=False,
                          print_radl=True, json=False, yes=True, destroy=False)
        with self.assertRaises(SystemExit) as ex1:
            CmdLaunch.run(options)
        self.assertEquals("1" ,str(ex1.exception))

        cluster_store.list.return_value = []
        with self.assertRaises(SystemExit) as ex2:
            CmdLaunch.run(options)
        self.assertEquals("0" ,str(ex2.exception))

        radl = """system front (
  net_interface.1.dns_name = 'kubeserverpublic' and
  disk.0.os.credentials.username = 'ubuntu' and
  disk.0.applications contains (
    name = 'ansible.modules.grycap.kubernetes'
  ) and
  disk.0.applications contains (
    name = 'ansible.modules.grycap.clues'
  ) and
  disk.0.applications contains (
    name = 'ansible.modules.grycap.im'
  ) and
  cpu.count >= 2 and
  net_interface.1.connection = 'public' and
  queue_system = 'kubernetes' and
  net_interface.0.dns_name = 'kubeserver' and
  instance_type = 't1.micro' and
  ec3_templates = 'im,clues2,kubernetes' and
  disk.0.image.url = 'aws://us-east-1/ami-30519058' and
  auth = 'username = user ; password = pass ; type = InfrastructureManager
' and
  net_interface.0.connection = 'private' and
  memory.size >= 2048m and
  disk.0.os.name = 'linux' and
  ec3_templates_cmd = 'ubuntu-ec2 kubernetes'
)

system wn (
  disk.0.image.url = 'aws://us-east-1/ami-30519058' and
  instance_type = 't1.micro' and
  ec3_max_instances = 10 and
  memory.size >= 2048m and
  net_interface.0.connection = 'private' and
  disk.0.os.name = 'linux' and
  disk.0.os.credentials.username = 'ubuntu'
)

network public (
  outbound = 'yes' and
  outports = '6443/tcp,8800/tcp'
)

network private (

)

configure front (
@begin
- tasks:
  - iptables:
      action: insert
      chain: INPUT
      destination_port: '{{item|dirname}}'
      jump: ACCEPT
      protocol: '{{item|basename}}'
    when: ansible_os_family == "RedHat"
    with_items: '{{OUTPORTS.split('','')}}'
  - firewalld:
      immediate: true
      permanent: true
      port: '{{item}}'
      state: enabled
    ignore_errors: true
    when: ansible_os_family == "RedHat"
    with_items: '{{OUTPORTS.split('','')}}'
  vars:
    OUTPORTS: 6443/tcp,8800/tcp
- roles:
  - kube_api_server: '{{ IM_NODE_PRIVATE_IP }}'
    kube_apiserver_options:
    - option: --insecure-port
      value: '8080'
    kube_server: kubeserver
    role: grycap.kubernetes
- roles:
  - role: grycap.im
- roles:
  - auth: '{{AUTH}}'
    clues_queue_system: '{{QUEUE_SYSTEM}}'
    max_number_of_nodes: '{{ NNODES }}'
    role: grycap.clues
    vnode_prefix: wn
  vars:
    AUTH: 'username = user ; password = pass ; type = InfrastructureManager

      '
    NNODES: '{{ SYSTEMS | selectattr("ec3_max_instances_max", "defined") | sum(attribute="ec3_max_instances_max")
      }}'
    QUEUE_SYSTEM: kubernetes
    SYSTEMS:
    - auth: 'username = user ; password = pass ; type = InfrastructureManager

        '
      class: system
      cpu.count_max: inf
      cpu.count_min: 2
      disk.0.applications:
      - name: ansible.modules.grycap.kubernetes
      - name: ansible.modules.grycap.clues
      - name: ansible.modules.grycap.im
      disk.0.image.url: aws://us-east-1/ami-30519058
      disk.0.os.credentials.username: ubuntu
      disk.0.os.name: linux
      ec3_templates:
      - im
      - clues2
      - kubernetes
      ec3_templates_cmd: ubuntu-ec2 kubernetes
      id: front
      instance_type: t1.micro
      memory.size_max: inf
      memory.size_min: 2048
      net_interface.0.connection:
        class: network
        id: private
        reference: true
      net_interface.0.dns_name: kubeserver
      net_interface.1.connection:
        class: network
        id: public
        reference: true
      net_interface.1.dns_name: kubeserverpublic
      queue_system: kubernetes
    - class: network
      id: public
      outbound: 'yes'
      outports:
      - 6443/tcp
      - 8800/tcp
    - class: network
      id: private
    - class: system
      disk.0.image.url: aws://us-east-1/ami-30519058
      disk.0.os.credentials.username: ubuntu
      disk.0.os.name: linux
      ec3_max_instances_max: 10
      ec3_max_instances_min: 10
      id: wn
      instance_type: t1.micro
      memory.size_max: inf
      memory.size_min: 2048
      net_interface.0.connection:
        class: network
        id: private
        reference: true

@end
)

configure wn (
@begin
- tasks:
  - iptables:
      action: insert
      chain: INPUT
      destination_port: '{{item|dirname}}'
      jump: ACCEPT
      protocol: '{{item|basename}}'
    when: ansible_os_family == "RedHat"
    with_items: '{{OUTPORTS.split('','')}}'
  - firewalld:
      immediate: true
      permanent: true
      port: '{{item}}'
      state: enabled
    ignore_errors: true
    when: ansible_os_family == "RedHat"
    with_items: '{{OUTPORTS.split('','')}}'
  vars:
    OUTPORTS: 6443/tcp,8800/tcp
- roles:
  - kube_server: kubeserver
    kube_type_of_node: wn
    role: grycap.kubernetes

@end
)

deploy front 1
"""

        if sys.version_info < (3, 0):
            self.assertEquals(display.call_args_list[1][0][0], radl)

        requests.side_effect = self.get_response
        options = Options(not_store=False, clustername="name", auth_file=auth_file, restapi=['http://server.com:8800'],
                          dry_run=False, templates=['ubuntu-ec2','kubernetes'], add=False, golden_image=False,
                          print_radl=False, json=False, yes=True, destroy=False)

        with self.assertRaises(SystemExit) as ex2:
            CmdLaunch.run(options)
        self.assertEquals("0" ,str(ex2.exception))

        self.assertEquals(display.call_args_list[4][0][0], "Infrastructure successfully created with ID: infid")
        self.assertEquals(display.call_args_list[5][0][0], "Front-end configured with IP 8.8.8.8")
        self.assertEquals(display.call_args_list[6][0][0], "Transferring infrastructure")
        self.assertEquals(display.call_args_list[7][0][0], "Front-end ready!")

    def test_templates(self):
        Options = namedtuple('Options', ['search', 'name', 'json', 'full'])
        options = Options(search=[None], name=[None], json=False, full=False)
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        CmdTemplates.run(options)
        res = sys.stdout.getvalue()
        sys.stdout = old_stdout
        self.assertIn("          name              kind                                         summary                                      \n", res)
        self.assertIn("----------------------------------------------------------------------------------------------------------------------\n", res)
        self.assertIn("         galaxy           component Galaxy is an open, web-based platform for data intensive biomedical research.     \n", res)

    @patch('requests.request')
    @patch('ec3.ClusterStore')
    @patch('ec3.CLI.display')
    def test_destroy(self, display, cluster_store, requests):
        cluster_store.list.return_value = []
        Options = namedtuple('Options', ['restapi', 'json', 'clustername', 'force', 'yes', 'auth_file'])
        options = Options(restapi=['http://server.com:8800'], json=False, clustername='name', force=True, yes=True,
                          auth_file=[])
        with self.assertRaises(SystemExit) as ex:
            CmdDestroy.run(options)
        self.assertEquals("1" ,str(ex.exception))
        
        cluster_store.list.return_value = ["name"]
        radl = RADL()
        n = network("public")
        n.setValue("outbound", "yes")
        s = system("front")
        s.setValue("ec3aas.username", "user")
        s.setValue("state", "configured")
        s.setValue("nodes", "1")
        s.setValue("net_interface.0.connection", n)
        s.setValue("net_interface.0.ip", "8.8.8.8")
        radl.add(s)
        cluster_store.load.return_value = radl
        auth = [{"type": "InfrastructureManager", "username": "user", "password": "pass"}]
        cluster_store.get_im_server_infrId_and_vmId_and_auth.return_value = "http://server.com", "infid", "", auth
        requests.side_effect = self.get_response

        with self.assertRaises(SystemExit) as ex:
            CmdDestroy.run(options)
        self.assertEquals("0" ,str(ex.exception))

    @patch('requests.request')
    @patch('os.listdir')
    @patch('os.makedirs')
    @patch(open_name, new_callable=mock_open, read_data=cluster_data)
    def test_cluster_store(self, mo, makedirs, listdirs, requests):
        listdirs.return_value = ["cluster1"]
        res = ClusterStore.list()
        self.assertEqual(["cluster1"], res)

        requests.side_effect = self.get_response
        res = ClusterStore.load("cluster1", True)
        s = res.get(system("front"))
        self.assertEqual(s.getValue("__infrastructure_id"), "infid")
        self.assertIn(".ec3/clusters/cluster1", mo.call_args_list[-1][0][0])
        if sys.version_info < (3, 0):
            expected_res = """network public (\n  outbound = \'yes\'\n)\n\nsystem front (\n  net_interface.0.ip = \'8.8.8.8\' and\n  __infrastructure_id = \'infid\' and\n  auth = \'[{"type": "InfrastructureManager", "username": "user", "password": "pass"}]\' and\n  __im_server = \'http://server.com:8800\' and\n  net_interface.0.connection = \'public\' and\n  nodes = 1 and\n  contextualization_output = \'contmsg\'\n)"""
            self.assertEqual(mo.mock_calls[-2][1][0], expected_res)

if __name__ == "__main__":
    unittest.main()