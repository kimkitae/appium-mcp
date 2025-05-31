import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from src.iphone_simulator import Simctl
except Exception:  # pragma: no cover - skip if dependency missing
    Simctl = None  # type: ignore

class TestSimctlParsing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if Simctl is None:
            raise unittest.SkipTest("Simctl dependency missing")
    def test_parse_listapps_output(self):
        text = """
                {
                        ".xctrunner" =     {
                                ApplicationType = User;
                                Bundle = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Bundle/Application/8EB6C622-A298-4BB6-8E29-AA2A5CE062EF/WebDriverAgentRunner-Runner.app/";
                                BundleContainer = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Bundle/Application/8EB6C622-A298-4BB6-8E29-AA2A5CE062EF/";
                                CFBundleDisplayName = "WebDriverAgentRunner-Runner";
                                CFBundleExecutable = "WebDriverAgentRunner-Runner";
                                CFBundleIdentifier = ".xctrunner";
                                CFBundleName = "WebDriverAgentRunner-Runner";
                                CFBundleVersion = 1;
                                DataContainer = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Data/Application/AE7D36A1-AACA-4171-A070-645992DEAEB9/";
                                GroupContainers =         {
                                };
                                Path = "/Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Bundle/Application/8EB6C622-A298-4BB6-8E29-AA2A5CE062EF/WebDriverAgentRunner-Runner.app";
                                SBAppTags =         (
                                );
                        };
                        "com.mobilenext.sample1" =     {
                                ApplicationType = System;
                                Bundle = "file:///Library/Developer/CoreSimulator/Volumes/iOS_22D8075/Library/Developer/CoreSimulator/Profiles/Runtimes/iOS 18.3.simruntime/Contents/Resources/RuntimeRoot/Applications/Bridge.app/";
                                CFBundleDisplayName = Sample1;
                                CFBundleExecutable = Sample1;
                                CFBundleIdentifier = "com.mobilenext.sample1";
                                CFBundleName = "Sample{1}App";
                                CFBundleVersion = "1.0";
                                DataContainer = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Data/Application/0D5C84C1-044C-4C03-B443-A1416DC1A296/";
                                GroupContainers =         {
                                        "243LU875E5.groups.com.apple.podcasts" = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Shared/AppGroup/8B2DA97D-2308-4B65-B87F-1E71493477E5/";
                                        "group.com.apple.bridge" = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Shared/AppGroup/F6E42206-B548-4F83-AB13-6E5BD7D69AB0/";
                                        "group.com.apple.iBooks" = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Shared/AppGroup/EEBEC72A-6673-446A-AB31-E154AB850B69/";
                                        "group.com.apple.mail" = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Shared/AppGroup/C3339457-EB6A-46D1-92A3-AE398DA8CAC5/";
                                        "group.com.apple.stocks" = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Shared/AppGroup/50E3741D-E249-421F-83E8-24A896A1245B/";
                                        "group.com.apple.weather" = "file:///Library/Developer/CoreSimulator/Devices/FB9D9985-8FD0-493D-9B09-58FD3AA4BE65/data/Containers/Shared/AppGroup/28D40933-57F1-4B65-864F-1F6538B3ADF9/";
                                };
                                Path = "/Library/Developer/CoreSimulator/Volumes/iOS_22D8075/Library/Developer/CoreSimulator/Profiles/Runtimes/iOS 18.3.simruntime/Contents/Resources/RuntimeRoot/Applications/Bridge.app";
                                SBAppTags =         (
                                        "watch-companion"
                                );
                        };
                }
                """
        apps = Simctl.parse_ios_app_data(text)
        self.assertEqual(len(apps), 2)
        self.assertEqual(apps[0].cf_bundle_display_name, "WebDriverAgentRunner-Runner")
        self.assertEqual(apps[1].cf_bundle_display_name, "Sample1")
        self.assertEqual(apps[1].cf_bundle_name, "Sample{1}App")

if __name__ == "__main__":
    unittest.main()
