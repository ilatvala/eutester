#!/usr/bin/python
# -*- coding: utf-8 -*-
# Software License Agreement (BSD License)
#
# Copyright (c) 2009-2011, Eucalyptus Systems, Inc.
# All rights reserved.
#
# Redistribution and use of this software in source and binary forms, with or
# without modification, are permitted provided that the following conditions
# are met:
#
#   Redistributions of source code must retain the above
#   copyright notice, this list of conditions and the
#   following disclaimer.
#
#   Redistributions in binary form must reproduce the above
#   copyright notice, this list of conditions and the
#   following disclaimer in the documentation and/or other
#   materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Author: vic.iglesias@eucalyptus.com


__version__ = '0.0.1'

import re
import paramiko
import boto
import random
import time
import signal
from bm_machine import bm_machine

class Eutester:
    def __init__(self, config_file="cloud.conf", hostname="clc", password="foobar", keypath=None, credpath=None, debug=0):
        """  
        EUCADIR => $eucadir, 
        VERIFY_LEVEL => $verify_level, 
        TOOLKIT => $toolkit, 
        DELAY => $delay, 
        FAIL_COUNT => $fail_count, 
        INPUT_FILE => $input_file, 
        PASSWORD => $password }
        , credpath=None, timeout=30, exit_on_fail=0
        EucaTester takes 2 arguments to their constructor
        1. Configuration file to use
        2. Eucalyptus component to connect to [CLC NC00 SC WS CC00] or a hostname
        3. Password to connect to the host
        4. 
        """
        self.config_file = config_file        
        self.password = password
        self.keypath = keypath
        #self.starttime = time()
        self.credpath = credpath
        self.timeout = 30
        self.delay = 0
        self.exit_on_fail = 0
        self.exit_on_fail = 0
        self.fail_count = 0
        self.start_time = time.time()
        self.key_dir = "./keypairs"
        ### Read input file
        config = self.read_config(config_file)
        self.eucapath = "/opt/eucalyptus"
        print config["machines"]
        if "REPO" in config["machines"][0].source:
            self.eucapath="/"
        ## CHOOSE A RANDOM HOST OF THIS COMPONENT TYPE
        if len(hostname) < 5:
            # Get a list of hosts with this role
            machines_with_role = [machine.hostname for machine in config['machines'] if hostname in machine.components]
            hostname = random.choice(machines_with_role)
            self.hostname = hostname
        ### SETUP SSH CLIENT
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())            
        if keypath == None:
            client.connect(self.hostname, username="root", password=password)
        else:
            client.connect(self.hostname,  username="root", keyfile_name=keypath)
        ### GET CREDENTIALS
        self.clc_ssh = client    
        if credpath == None:    
            admin_cred_dir = "eucarc-eucalyptus-admin"
            cmd_download_creds = self.eucapath + "/usr/sbin/euca_conf --get-credentials " + admin_cred_dir + "/creds.zip " + "--cred-user admin --cred-account eucalyptus" 
            cmd_setup_cred_dir = ["rm -rf " + admin_cred_dir,"mkdir " + admin_cred_dir ,  cmd_download_creds , "unzip " + admin_cred_dir + "/creds.zip -d " + admin_cred_dir, "ls " + admin_cred_dir]
            for cmd in cmd_setup_cred_dir:         
                stdout = self.sys(cmd)
            self.credpath = admin_cred_dir
        print self
        boto_access = self.get_access_key()
        boto_secret = self.get_secret_key()
        self.debug = debug
        self.ec2 = boto.connect_euca(host=self.hostname, aws_access_key_id=boto_access, aws_secret_access_key=boto_secret, debug=self.debug)
        self.walrus = boto.connect_walrus(host=self.hostname, aws_access_key_id=boto_access, aws_secret_access_key=boto_secret, debug=self.debug)
               
        ### read the input file and return the config object/hash whatever it needs to be
    def get_access_key(self):
        access_key = self.sys( "cat ./" + self.credpath + "/eucarc | grep export | grep ACCESS | awk 'BEGIN { FS = \"=\" } ; { print $2 }' ")        
        return access_key[0].strip().strip("'")
    
    def get_secret_key(self):
        secret_key = self.sys("cat ./" + self.credpath + "/eucarc | grep export | grep SECRET | awk 'BEGIN { FS = \"=\" } ; { print $2 }' ")      
        return secret_key[0].strip().strip("'")
    
    def add_keypair(self,key_name="keypair-" + str(int(time.time())) ):
        print "Looking up keypair " + key_name 
        key = self.ec2.get_all_key_pairs(keynames=[key_name])    
        if key == []:
            print 'Creating keypair: %s' % key_name
            # Create an SSH key to use when logging into instances.
            key = self.ec2.create_key_pair(key_name)
        
            # AWS will store the public key but the private key is
            # generated and returned and needs to be stored locally.
            # The save method will also chmod the file to protect
            # your private key.
            key.save(self.key_dir)
            return key
        else:
            print "Key " + key_name + " already exists"
    
    def add_group(self, group_name="group-" + str(int(time.time())) ):
        print "Looking up group " + group_name
        group = self.ec2.get_all_security_groups(groupnames=[group_name])        
        if group == []:
            print 'Creating Security Group: %s' % group_name
            # Create a security group to control access to instance via SSH.
            group = self.ec2.create_security_group(group_name, group_name)
            return group
        else:
             print "Group " + group_name + " already exists"
             return group[0]
    
    def read_config(self, filepath):
        config_hash = {}
        machines = []
        f = None
        try:
            f = open(filepath, 'r')
        except IOError as (errno, strerror):
            print "ERROR: Could not find config file " + self.config_file
            exit(1)
            #print "I/O error({0}): {1}".format(errno, strerror)
            
        for line in f:
            ### LOOK for the line that is defining a machine description
            line = line.strip()
            re_machine_line = re.compile(".*\[.*]")
            if re_machine_line.match(line):
                #print "Matched Machine :" + line
                machine_details = line.split(None, 5)
                machine_dict = {}
                machine_dict["hostname"] = machine_details[0]
                machine_dict["distro"] = machine_details[1]
                machine_dict["distro_ver"] = machine_details[2]
                machine_dict["arch"] = machine_details[3]
                machine_dict["source"] = machine_details[4]
                machine_dict["components"] = map(str.lower, machine_details[5].strip('[]').split())
                ### ADD the machine to the array of machine
                machine = bm_machine(machine_dict["hostname"], machine_dict["distro"], machine_dict["distro_ver"], machine_dict["arch"], machine_dict["source"], machine_dict["components"])
                machines.append(machine)
                print machine
            if line.find("NETWORK"):
                config_hash["network"] = line.strip()
        config_hash["machines"] = machines 
        return config_hash
    
    def fail(self, message):
        print "[TEST_REPORT] FAILED: " + message
        self.fail_count += 1
        if self.exit_on_fail == 1:
            exit(1)
        else:
            return 0   
         
    def timeout_handler(self, signum, frame):
        self.fail("Command timeout after " + self.timeout + " seconds")
        raise Exception("Timeout Reached")
    
    def do_exit(self):       
        exit_report  = "******************************************************\n"
        exit_report += "*" + "Failures:" + str(self.fail_count) + "\n"
        exit_report += "*" + "Time to execute: " + str(self.get_exectuion_time()) +"\n"
        exit_report += "******************************************************\n"
        print exit_report
        if self.fail_count > 0:
            exit(1)
        else:
            exit(0)
            
    def sys(self, cmd):
        time.sleep(self.delay)
        signal.signal(signal.SIGALRM, self.timeout_handler ) 
        signal.alarm(self.timeout) # triger alarm in timeout seconds
        cur_time = time.strftime("%I:%M:%S", time.gmtime())
        print "[root@" + self.hostname + "-" + cur_time +"]# " + cmd
        try:
            if self.credpath != None:
                cmd = ". " + self.credpath + "/eucarc && " + cmd
            stdin, stdout, stderr = self.clc_ssh.exec_command(cmd)   
        except Exception, e:
            self.fail("Command timeout after " + str(self.timeout) + " seconds\nException:" + str(e)) 
            print e
            return
        signal.alarm(0)
        output = stdout.readlines()
        print "".join(stderr.readlines()) + "".join(output) 
        return output
    
    def test_name(self, message):
        print "[TEST_REPORT] " + message
    
    def get_exectuion_time(self):
        return time.time() - self.start_time
    
    def set_config_file(self, filepath):
        self.config_file = filepath
    
    def get_config_file(self):
        return self.config_file
        
    def set_host(self, host):
        self.host = host
    
    def get_host(self):
        return self.host
    
    def set_credpath(self, path):
        self.credpath = path
    
    def get_credpath(self):
        return self.credpath
        
    def set_timeout(self, seconds):
        self.timeout = seconds
    
    def get_timeout(self):
        return self.timeout
            
    def set_eucapath(self, path):
        self.config_file = path
    
    def get_eucapath(self):
        return self.eucapath
    
    def set_exit_on_fail(self, exit_on_fail):
        self.exit_on_fail = exit_on_fail
    
    def get_exit_on_fail(self):
        return self.exit_on_fail
    
    def clear_fail_count(self):
        self.fail_count = 0
        
    def set_delay(self, delay):
        self.delay = delay
    
    def get_delay(self):
        return self.delay
    
    def __str__(self):
        s  = "+++++++++++++++++++++++++++++++++++++++++++++++++++++\n"
        s += "+" + "Host:" + self.hostname + "\n"
        s += "+" + "Config File: " + self.config_file +"\n"
        s += "+" + "Fail Count: " +  str(self.fail_count) +"\n"
        s += "+" + "Eucalyptus Path: " +  str(self.eucapath) +"\n"
        s += "+" + "Credential Path: " +  str(self.credpath) +"\n"
        s += "+++++++++++++++++++++++++++++++++++++++++++++++++++++"
        return s