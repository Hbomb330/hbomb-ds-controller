import subprocess
import unittest
from unittest.mock import patch
import bluetooth_diagnostics as bt

class BluetoothTests(unittest.TestCase):
    def test_missing_tool(self):
        with patch.object(bt.shutil, 'which', return_value=None):
            self.assertIn('missing', bt.bluetooth_report())
    def test_redaction_and_read_only_commands(self):
        calls=[]
        def run(args):
            calls.append(args)
            if args[1]=='devices':
                return 'Device AA:BB:CC:DD:EE:FF Xbox Wireless Controller'
            return 'Connected: yes\nAddress: AA:BB:CC:DD:EE:FF'
        with patch.object(bt.shutil, 'which', return_value='/usr/bin/bluetoothctl'), patch.object(bt, 'run_command', side_effect=run):
            report=bt.bluetooth_report()
        self.assertNotIn('AA:BB:CC:DD:EE:FF', report)
        self.assertIn('Connected: yes', report)
        self.assertEqual([c[1] for c in calls], ['show','devices','info'])
    def test_timeout(self):
        with patch.object(bt.subprocess, 'run', side_effect=subprocess.TimeoutExpired('bluetoothctl',5)):
            self.assertIn('timed out', bt.run_command(['bluetoothctl','show']))

if __name__=='__main__':
    unittest.main()
