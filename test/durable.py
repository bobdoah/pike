#
# Copyright (c) 2013, EMC Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
#
# Module Name:
#
#        durable.py
#
# Abstract:
#
#        Durable handle tests
#
# Authors: Arlene Berry (arlene.berry@emc.com)
#

import pike.model
import pike.smb2
import pike.test
import pike.ntstatus
import random
import array

@pike.test.RequireCapabilities(pike.smb2.SMB2_GLOBAL_CAP_LEASING)
class DurableHandleTest(pike.test.PikeTest):
    share_all = pike.smb2.FILE_SHARE_READ | pike.smb2.FILE_SHARE_WRITE | pike.smb2.FILE_SHARE_DELETE
    lease1 = array.array('B',map(random.randint, [0]*16, [255]*16))
    lease2 = array.array('B',map(random.randint, [0]*16, [255]*16))
    r = pike.smb2.SMB2_LEASE_READ_CACHING
    rw = r | pike.smb2.SMB2_LEASE_WRITE_CACHING
    rh = r | pike.smb2.SMB2_LEASE_HANDLE_CACHING
    rwh = rw | rh
                    
    def create(self, chan, tree, durable, lease=rwh, lease_key=lease1, disposition=pike.smb2.FILE_SUPERSEDE):
        return chan.create(tree,
                           'durable.txt',
                           access=pike.smb2.FILE_READ_DATA | pike.smb2.FILE_WRITE_DATA | pike.smb2.DELETE,
                           share=self.share_all,
                           disposition=disposition,
                           oplock_level=pike.smb2.SMB2_OPLOCK_LEVEL_LEASE,
                           lease_key = lease_key,
                           lease_state = lease,
                           durable=durable).result()

    def durable_test(self, durable):
        chan, tree = self.tree_connect()

        handle1 = self.create(chan, tree, durable=durable)

        self.assertEqual(handle1.lease.lease_state, self.rwh)

        chan.close(handle1)

    def durable_reconnect_test(self, durable):
        chan, tree = self.tree_connect()

        handle1 = self.create(chan, tree, durable=durable)

        self.assertEqual(handle1.lease.lease_state, self.rwh)

        # Close the connection
        chan.connection.close()

        chan2, tree2 = self.tree_connect()

        # Request reconnect
        handle2 = self.create(chan2, tree2, durable=handle1)
    
        self.assertEqual(handle2.lease.lease_state, self.rwh)

        chan2.close(handle2)

    def durable_reconnect_fails_client_guid_test(self, durable):
        chan, tree = self.tree_connect()

        handle1 = self.create(chan, tree, durable=durable)

        self.assertEqual(handle1.lease.lease_state, self.rwh)

        # Close the connection
        chan.connection.close()

        chan2, tree2 = self.tree_connect(client=pike.model.Client())

        with self.assert_error(pike.ntstatus.STATUS_OBJECT_NAME_NOT_FOUND):
            handle2 = self.create(chan2, tree2, durable=handle1)

        chan2.connection.close()

        chan3, tree3 = self.tree_connect()

        handle3 = self.create(chan3, tree3, durable=handle1)

        chan3.close(handle3)

    def durable_invalidate_test(self, durable):
        chan, tree = self.tree_connect()

        handle1 = self.create(chan, tree, durable=durable, lease=self.rw)
        self.assertEqual(handle1.lease.lease_state, self.rw)

        # Close the connection
        chan.connection.close()

        chan2, tree2 = self.tree_connect(client=pike.model.Client())

        # Invalidate handle from separate client
        handle2 = self.create(chan2,
                              tree2,
                              durable=durable,
                              lease=self.rw,
                              lease_key=self.lease2,
                              disposition=pike.smb2.FILE_OPEN)
        self.assertEqual(handle2.lease.lease_state, self.rw)
        chan2.close(handle2)

        chan2.connection.close()

        chan3, tree3 = self.tree_connect()

        # Reconnect should now fail
        with self.assert_error(pike.ntstatus.STATUS_OBJECT_NAME_NOT_FOUND):
            handle3 = self.create(chan3, tree3, durable=handle1)

    # Request a durable handle
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB2_1)
    def test_durable(self):
        self.durable_test(True)

    # Reconnect a durable handle after a TCP disconnect
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB2_1)
    def test_durable_reconnect(self):
        self.durable_reconnect_test(True)

    # Reconnecting a durable handle after a TCP disconnect
    # fails with STATUS_OBJECT_NAME_NOT_FOUND if the client
    # guid does not match
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB2_1)
    def test_durable_reconnect_fails_client_guid(self):
        self.durable_reconnect_fails_client_guid_test(True)

    # Breaking the lease of a disconnected durable handle
    # (without HANDLE) invalidates it, so a subsequent
    # reconnect will fail.
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB2_1)
    def test_durable_invalidate(self):
        self.durable_invalidate_test(True)

    # Request a durable handle via V2 context structure
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB3_0)
    def test_durable_v2(self):
        self.durable_test(0)

    # Reconnect a durable handle via V2 context structure
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB3_0)
    def test_durable_reconnect_v2(self):
        self.durable_reconnect_test(0)

    # Reconnecting a durable handle (v2) after a TCP disconnect
    # fails with STATUS_OBJECT_NAME_NOT_FOUND if the client
    # guid does not match
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB3_0)
    def test_durable_reconnect_v2_fails_client_guid(self):
        self.durable_reconnect_fails_client_guid_test(0)

    # Breaking the lease of a disconnected durable handle v2
    # (without HANDLE) invalidates it, so a subsequent
    # reconnect will fail.
    @pike.test.RequireDialect(pike.smb2.DIALECT_SMB3_0)
    def test_durable_v2_invalidate(self):
        self.durable_invalidate_test(0)
