import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import linux_inventory as inv

FIXTURE = '''I: Bus=0005 Vendor=054c Product=0268 Version=0100
N: Name="Sony PLAYSTATION(R)3 Controller"
H: Handlers=event6 js0

I: Bus=0003 Vendor=045e Product=0b12 Version=0100
N: Name="Xbox Wireless Controller"
H: Handlers=event7 js1

I: Bus=0003 Vendor=045e Product=0001 Version=0100
N: Name="Microsoft Keyboard"
H: Handlers=kbd event8
'''

class InventoryTests(unittest.TestCase):
    def test_transports_and_keyboard_exclusion(self):
        rows = inv.parse_inputs(FIXTURE)
        self.assertEqual([r['transport'] for r in rows], ['Bluetooth', 'USB'])
        self.assertEqual(len(rows), 2)
    def test_unmapped_and_unknown_bus(self):
        rows = inv.parse_inputs(FIXTURE.replace('0005', '0006').replace('event6 js0', 'event6'))
        self.assertEqual(rows[0]['transport'], 'other/unknown')
    def test_malformed(self):
        self.assertEqual(inv.parse_inputs('permission denied'), [])
    def test_radio_advice(self):
        self.assertTrue(any('radio-blocked' in s for s in inv.advice('Soft blocked: yes', [])))
        self.assertTrue(any('powered off' in s for s in inv.advice('Powered: no', [])))
        self.assertTrue(any('disconnected' in s for s in inv.advice('Connected: no', [])))
    def test_command_timeout(self):
        with patch.object(inv.subprocess, 'run', side_effect=subprocess.TimeoutExpired('x', 4)):
            self.assertIn('UNKNOWN', inv.Runner()(['bluetoothctl','list']))
    def test_missing_command(self):
        with patch.object(inv.subprocess, 'run', side_effect=FileNotFoundError()):
            self.assertIn('UNKNOWN', inv.Runner()(['bluetoothctl','list']))
    def test_exit_and_locale(self):
        with patch.object(inv.subprocess, 'run', return_value=subprocess.CompletedProcess([],1,'','denied')) as run:
            self.assertIn('UNKNOWN', inv.Runner()(['rfkill','list','bluetooth']))
            self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C')
            self.assertNotIn('shell', run.call_args.kwargs)
    def test_budget(self):
        with patch.object(inv.subprocess, 'run') as run:
            self.assertIn('budget', inv.Runner(-1)(['bluetoothctl','list']))
            run.assert_not_called()
    def test_adapter_usb_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); usb=root/'usb'; usb.mkdir()
            (usb/'idVendor').write_text('8087'); (usb/'idProduct').write_text('0026')
            (root/'hci0').mkdir(); (root/'hci0'/'device').symlink_to(usb)
            self.assertIn('8087:0026', inv.adapter_inventory(root)[0])
    def test_read_only_report_redacts_and_lists_two_adapters(self):
        calls=[]
        def run(args):
            calls.append(args)
            if args == ['bluetoothctl','list']:
                return 'Controller AA:BB:CC:DD:EE:FF Primary\nController 11:22:33:44:55:66 Other'
            if args == ['bluetoothctl','devices']:
                return 'Device AA:BB:CC:DD:EE:00 Xbox Wireless Controller'
            return 'Connected: yes'
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'input'; path.write_text(FIXTURE)
            report=inv.report(run, path, tmp)
        self.assertNotIn('AA:BB:', report)
        self.assertEqual(len([c for c in calls if c[:2]==['bluetoothctl','show']]), 2)
        for command in calls:
            self.assertIn(tuple(command[:2]), [('rfkill','list'),('systemctl','is-active'),('bluetoothctl','--version'),('bluetoothctl','list'),('bluetoothctl','show'),('bluetoothctl','devices'),('bluetoothctl','info'),('modinfo','-F')])
        self.assertIn('Sony PLAYSTATION', report)
        self.assertIn('USB', report)

if __name__=='__main__': unittest.main()
