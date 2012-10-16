#!/usr/bin/env python
#
#
# Description:  This script encompasses test cases/modules concerning instance specific behavior and
#               features for Eucalyptus.  The test cases/modules that are executed can be
#               found in the script under the "tests" list.


import time
from eucaops import Eucaops
from eutester.euinstance import EuInstance
from eutester.eutestcase import EutesterTestCase
import os
import random


class InstanceRestore(EutesterTestCase):
    def __init__(self, config_file=None, password=None):
        self.setuptestcase()
        # Setup basic eutester object
        self.tester = Eucaops( config_file=config_file, password=password)
        self.tester.poll_count = 120

        ### Add and authorize a group for the instance
        self.group = self.tester.add_group(group_name="group-" + str(time.time()))
        self.tester.authorize_group_by_name(group_name=self.group.name )
        self.tester.authorize_group_by_name(group_name=self.group.name, port=-1, protocol="icmp" )
        ### Generate a keypair for the instance
        self.keypair = self.tester.add_keypair( "keypair-" + str(time.time()))
        self.keypath = '%s/%s.pem' % (os.curdir, self.keypair.name)
        self.image = self.tester.get_emi(root_device_type="instance-store")
        self.reservation = None
        self.private_addressing = False
        zones = self.tester.ec2.get_all_zones()
        self.zone = random.choice(zones).name

        self.cur_time = str(int(time.time()))

    def clean_method(self):
        ncs = self.tester.get_component_machines("nc")
        for nc in ncs:
            nc.sys("service eucalyptus-nc start")

        if self.reservation:
            self.assertTrue(self.tester.terminate_instances(self.reservation), "Unable to terminate instance(s)")
        self.tester.delete_group(self.group)
        self.tester.delete_keypair(self.keypair)
        os.remove(self.keypath)

    def restore_logic(self):
        self.reservation = self.tester.run_instance(self.image, keypair=self.keypair.name, group=self.group.name, zone=self.zone)
        ncs = self.tester.get_component_machines("nc")
        for nc in ncs:
            nc.sys("service eucalyptus-nc stop")

        ### Wait for instance to show up as terminating
        self.tester.wait_for_reservation(self.reservation, state="terminated", timeout=900)

        ### Wait for reservation to disappear
        while len(self.tester.get_instances(reservation=self.reservation)) > 0:
            self.tester.sleep(30)

        self.tester.deregister_image(self.image)

        for nc in ncs:
            nc.sys("service eucalyptus-nc start")

        self.tester.wait_for_reservation(self.reservation, state="running", timeout=900)
        for instance in self.reservation.instances:
            instance.sys("uname -r", code=0)

if __name__ == "__main__":
    testcase = EutesterTestCase()

    #### Adds argparse to testcase and adds some defaults args
    testcase.setup_parser()

    ### Get all cli arguments and any config arguments and merge them
    testcase.get_args()

    ### Instantiate an object of your test suite class using args found from above
    instance_basics_tests = testcase.do_with_args(InstanceRestore)

    ### Either use the list of tests passed from config/command line to determine what subset of tests to run
    list = testcase.args.tests or [ "restore_logic"]

    ### Convert test suite methods to EutesterUnitTest objects
    unit_list = [ ]
    for test in list:
        unit_list.append( instance_basics_tests.create_testunit_by_name(test) )

    ### Run the EutesterUnitTest objects
    testcase.run_test_case_list(unit_list)
    instance_basics_tests.clean_method()

__author__ = 'viglesias'
