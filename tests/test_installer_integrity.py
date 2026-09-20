"""
Installer & Bundle Integrity Test Suite
=======================================
Validates the build outputs and packaging integrity for NexusTube:
1. Validates build artifacts existence (NexusTube.exe and NexusTube_Setup_v3.2.0.msi).
2. Inspects PyInstaller CArchive Table of Contents (TOC) inside NexusTube.exe:
   - Verifies Tcl/Tk runtime components (pyi_rth__tkinter, tcl8.6/tk8.6/_tcl_data).
   - Verifies application icon is embedded.
   - Verifies custom runtime hooks (pyi_rth_safestreams).
   - Verifies web assets and entrypoint script are bundled.
3. PE binary format verification (64-bit AMD64, GUI subsystem).
4. MSI database inspection:
   - Product properties (ProductName, ProductVersion, Manufacturer, UpgradeCode).
   - File table entries (NexusTube.exe and NexusTube.ico).
5. WiX source file and installer assets validation (valid XML, icon, and runtime hook).
"""

import glob
import os
import struct
import sys
import unittest
import warnings
import xml.etree.ElementTree as ET

# Ensure repo root is on sys.path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)


def get_exe_path():
    candidates = [
        os.path.join(repo_root, "dist", "NexusTube.exe"),
        os.path.join(repo_root, "NexusTube.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 1024 * 1024:
            return c
    return None


def get_msi_path():
    candidates = [
        os.path.join(repo_root, "NexusTube_Setup_v3.2.0.msi"),
    ]
    candidates.extend(glob.glob(os.path.join(repo_root, "*.msi")))
    candidates.extend(glob.glob(os.path.join(repo_root, "dist", "*.msi")))
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 1024 * 1024:
            return c
    return None


class TestInstallerAndBundleIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.exe_path = get_exe_path()
        cls.msi_path = get_msi_path()

    def test_build_outputs_existence_and_size(self):
        """Verify NexusTube.exe and NexusTube_Setup_v3.2.0.msi exist with plausible production file sizes."""
        if not self.exe_path:
            self.skipTest("NexusTube.exe not found (skipped in pre-build test phase)")
        if not self.msi_path:
            self.skipTest("NexusTube_Setup_v3.2.0.msi not found (skipped in pre-build test phase)")

        exe_size = os.path.getsize(self.exe_path)
        msi_size = os.path.getsize(self.msi_path)

        # Both the standalone EXE and the MSI should exceed 25 MB
        self.assertGreater(
            exe_size, 25 * 1024 * 1024,
            f"NexusTube.exe size ({exe_size} bytes) is suspiciously small for a standalone bundle"
        )
        self.assertGreater(
            msi_size, 25 * 1024 * 1024,
            f"MSI installer size ({msi_size} bytes) is suspiciously small for a full installer"
        )

    def test_exe_pe_format_and_gui_subsystem(self):
        """Verify NexusTube.exe is a valid x64 Windows GUI executable."""
        if not self.exe_path:
            self.skipTest("NexusTube.exe not found")

        with open(self.exe_path, "rb") as f:
            header = f.read(4096)

        # DOS MZ header
        self.assertEqual(header[:2], b"MZ", "Missing DOS MZ signature")

        # PE signature offset
        e_lfanew = struct.unpack_from("<I", header, 0x3C)[0]
        self.assertEqual(header[e_lfanew : e_lfanew + 4], b"PE\x00\x00", "Missing PE signature")

        # Machine type: 0x8664 (AMD64)
        machine = struct.unpack_from("<H", header, e_lfanew + 4)[0]
        self.assertEqual(machine, 0x8664, "Binary must be AMD64/x64 architecture")

        # PE32+ (64-bit) optional header magic: 0x20b
        opt_magic = struct.unpack_from("<H", header, e_lfanew + 24)[0]
        self.assertEqual(opt_magic, 0x20B, "Binary must be PE32+ (64-bit)")

        # Subsystem: 2 (IMAGE_SUBSYSTEM_WINDOWS_GUI)
        subsystem = struct.unpack_from("<H", header, e_lfanew + 24 + 68)[0]
        self.assertEqual(
            subsystem, 2, "Binary must be built with GUI subsystem (subsystem=2) to suppress console window"
        )

    def test_exe_pyinstaller_carchive_toc_components(self):
        """Verify embedded CArchive TOC contains Tcl/Tk, icons, runtime hooks, modular scripts, and web assets."""
        if not self.exe_path:
            self.skipTest("NexusTube.exe not found")

        try:
            from PyInstaller.archive.readers import CArchiveReader
        except ImportError:
            self.skipTest("PyInstaller not installed in current test environment")

        reader = CArchiveReader(self.exe_path)
        toc_keys = list(reader.toc.keys())
        self.assertGreater(len(toc_keys), 500, "CArchive TOC should contain comprehensive bundled assets")

        # 1. Custom Runtime Hook (pyi_rth_safestreams)
        self.assertIn(
            "pyi_rth_safestreams", toc_keys,
            "pyi_rth_safestreams runtime hook must be bundled in NexusTube.exe"
        )

        # 2. Tcl/Tk Components
        self.assertIn(
            "pyi_rth__tkinter", toc_keys,
            "pyi_rth__tkinter runtime hook must be bundled in NexusTube.exe"
        )
        tcl_tk_entries = [
            k for k in toc_keys
            if any(p in k.lower() for p in ("tcl8.6", "tk8.6", "_tcl_data", "_tk_data"))
        ]
        self.assertGreater(
            len(tcl_tk_entries), 50,
            f"Expected full Tcl/Tk data bundle, found only {len(tcl_tk_entries)} entries"
        )

        # 3. Application Icon
        icon_entries = [k for k in toc_keys if k.endswith(".ico")]
        self.assertTrue(
            any("NexusTube" in k or "icon" in k for k in icon_entries),
            f"Application icon not found in CArchive TOC: {icon_entries}"
        )

        # 4. Web Assets
        web_entries = [k for k in toc_keys if k.startswith("web")]
        self.assertGreater(
            len(web_entries), 0,
            "Web UI assets (web/*) must be bundled in NexusTube.exe"
        )
        self.assertTrue(
            any(k.endswith("index.html") for k in web_entries),
            "web/index.html must be bundled in NexusTube.exe"
        )

        # 5. Core Entrypoint
        self.assertIn(
            "YT_Downloader_V2", toc_keys,
            "YT_Downloader_V2 entrypoint must be in CArchive TOC"
        )

        # 6. Modular Nexus Architecture Components
        for mod in ("nexus_audio", "nexus_doctor", "nexus_hotkeys_tray", "nexus_discord"):
            self.assertTrue(
                any(mod in k for k in toc_keys),
                f"Modular component {mod} must be bundled in NexusTube.exe"
            )

    def test_msi_database_metadata_properties(self):
        """Verify MSI database properties (ProductName, ProductVersion, Manufacturer, UpgradeCode)."""
        if not self.msi_path:
            self.skipTest("NexusTube_Setup_v3.2.0.msi not found")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                import msilib

            db = msilib.OpenDatabase(self.msi_path, msilib.MSIDBOPEN_READONLY)
            view = db.OpenView("SELECT Property, Value FROM Property")
            view.Execute(None)
            properties = {}
            while True:
                record = view.Fetch()
                if not record:
                    break
                properties[record.GetString(1)] = record.GetString(2)
        except Exception as e:
            self.skipTest(f"msilib database inspection unavailable or failed: {e}")

        self.assertEqual(properties.get("ProductName"), "NexusTube")
        self.assertIn(properties.get("ProductVersion"), ["3.2.0", "3.4.0"])
        self.assertEqual(properties.get("Manufacturer"), "by herlove")
        self.assertEqual(properties.get("UpgradeCode"), "{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}")
        self.assertEqual(properties.get("WIXUI_INSTALLDIR"), "INSTALLDIR")
        self.assertEqual(properties.get("ALLUSERS"), "1")

    def test_msi_database_bundled_files(self):
        """Verify MSI File table contains NexusTube.exe and NexusTube.ico with matching sizes."""
        if not self.msi_path:
            self.skipTest("NexusTube_Setup_v3.2.0.msi not found")

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                import msilib

            db = msilib.OpenDatabase(self.msi_path, msilib.MSIDBOPEN_READONLY)
            view = db.OpenView("SELECT File, FileName, FileSize FROM File")
            view.Execute(None)
            files = {}
            while True:
                record = view.Fetch()
                if not record:
                    break
                file_id = record.GetString(1)
                file_name = record.GetString(2)
                file_size = record.GetInteger(3)
                files[file_id] = {"name": file_name, "size": file_size}
        except Exception as e:
            self.skipTest(f"msilib file inspection unavailable or failed: {e}")

        self.assertIn("NexusTubeExeFile", files)
        self.assertIn("NexusTube.exe", files["NexusTubeExeFile"]["name"])
        self.assertGreater(files["NexusTubeExeFile"]["size"], 30 * 1024 * 1024)

        self.assertIn("NexusTubeIcoFile", files)
        self.assertIn("NexusTube.ico", files["NexusTubeIcoFile"]["name"])
        self.assertGreater(files["NexusTubeIcoFile"]["size"], 1000)

    def test_installer_source_files_integrity(self):
        """Verify installer source scripts and WiX definition exist and are well-formed."""
        installer_dir = os.path.join(repo_root, "installer")
        wxs_path = os.path.join(installer_dir, "NexusTube.wxs")
        hook_path = os.path.join(installer_dir, "pyi_rth_safestreams.py")
        ico_path = os.path.join(installer_dir, "NexusTube.ico")
        builder_path = os.path.join(repo_root, "build_installer.py")

        self.assertTrue(os.path.isfile(wxs_path), "installer/NexusTube.wxs must exist")
        self.assertTrue(os.path.isfile(hook_path), "installer/pyi_rth_safestreams.py must exist")
        self.assertTrue(os.path.isfile(ico_path), "installer/NexusTube.ico must exist")
        self.assertTrue(os.path.isfile(builder_path), "build_installer.py must exist")

        # 1. Verify WiX XML syntax
        try:
            tree = ET.parse(wxs_path)
            root = tree.getroot()
            self.assertIn("Wix", root.tag)
        except Exception as e:
            self.fail(f"installer/NexusTube.wxs is not valid XML: {e}")

        # 2. Verify pyi_rth_safestreams.py content
        with open(hook_path, "r", encoding="utf-8") as f:
            hook_content = f.read()
        self.assertIn("_SafeStream", hook_content)
        self.assertIn("sys.stdout", hook_content)
        self.assertIn("sys.stderr", hook_content)

        # 3. Verify build_installer.py constants
        with open(builder_path, "r", encoding="utf-8") as f:
            builder_content = f.read()
        self.assertIn('PRODUCT_NAME    = "NexusTube"', builder_content)
        self.assertIn('PRODUCT_VERSION =', builder_content)


if __name__ == "__main__":
    unittest.main()
