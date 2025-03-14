import os
import subprocess
import time
import logging
import sys
import requests
from pathlib import Path
from datetime import datetime

# ==============================================
# WSA Profile Switcher - Manages WSA profiles
# ==============================================
#
# Automatic profiles detection and switching on every script execution
#
# Author: RoboCrax
# Date: 2025-03-04
# Version: 2.0
#
# ==============================================

class WSAProfileSwitcher:
    def __init__(self):
        self.local_appdata = os.getenv('LOCALAPPDATA')
        self.wsa_base = Path(self.local_appdata) / "Packages/MicrosoftCorporationII.WindowsSubsystemForAndroid_8wekyb3d8bbwe"
        self.wsa_client = Path(self.local_appdata) / "Microsoft/WindowsApps/MicrosoftCorporationII.WindowsSubsystemForAndroid_8wekyb3d8bbwe/WsaClient.exe"
        self.profiles_dir = self.wsa_base / "Tom_Profiles"
        self.queue_file = self.profiles_dir / "_queue.txt"
        self.current_profile = self.profiles_dir / "_active.txt"
        self.logfile = self.profiles_dir / "_logs.log"
        
        # Setup logging
        logging.basicConfig(
            filename=str(self.logfile),
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Also log to console
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
        console_handler.setFormatter(formatter)
        logging.getLogger().addHandler(console_handler)

    def check_admin(self):
        try:
            return os.getuid() == 0
        except AttributeError:
            import ctypes
            return ctypes.windll.shell32.IsUserAnAdmin() != 0

    def get_valid_profiles(self):
        profiles = []
        for vhdx_file in self.profiles_dir.glob("*.vhdx"):
            dat_file = vhdx_file.with_suffix('.dat')
            if dat_file.exists():
                profiles.append(vhdx_file.stem)
            else:
                logging.warning(f"Found orphaned VHDX file: {vhdx_file.name}")
        return profiles

    def read_queue(self):
        if self.queue_file.exists():
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def write_queue(self, queue):
        with open(self.queue_file, 'w', encoding='utf-8') as f:
            for profile in queue:
                f.write(f"{profile}\n")

    def update_queue(self):
        valid_profiles = self.get_valid_profiles()
        current_queue = self.read_queue()
        
        # Remove invalid profiles
        current_queue = [p for p in current_queue if p in valid_profiles]
        
        # Add new profiles
        for profile in valid_profiles:
            if profile not in current_queue:
                current_queue.append(profile)
        
        if not current_queue:
            current_queue = ["profile1"]
            logging.warning("No valid profiles found. Created default profile.")
        
        self.write_queue(current_queue)

    def stop_wsa(self):
        try:
            subprocess.run([str(self.wsa_client), "/shutdown"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logging.warning(f"First shutdown attempt failed: {e.stderr.decode()}")
        
        try:
            subprocess.run(["taskkill", "/F", "/IM", "WsaSettings.exe"], capture_output=True)
        except subprocess.CalledProcessError as e:
            logging.warning(f"Failed to terminate WsaSettings: {e.stderr.decode()}")
        
        time.sleep(2)
        
        try:
            subprocess.run([str(self.wsa_client), "/shutdown"], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            logging.warning(f"Second shutdown attempt failed: {e.stderr.decode()}")
        
        time.sleep(2)
        
        # Check for WSA processes
        wsa_processes = ["WsaClient.exe", "WsaSettings.exe"]
        for process in wsa_processes:
            result = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {process}"], 
                                  capture_output=True, text=True)
            if process in result.stdout:
                logging.warning(f"Process {process} is still running")
                try:
                    subprocess.run(["taskkill", "/F", "/IM", process], capture_output=True)
                except subprocess.CalledProcessError as e:
                    logging.warning(f"Failed to force terminate {process}: {e.stderr.decode()}")
        
        # Final check after force termination
        time.sleep(1)
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WsaClient.exe"], 
                              capture_output=True, text=True)
        if "WsaClient.exe" in result.stdout:
            logging.error("WSA processes still running after shutdown attempts")
            raise RuntimeError("Failed to stop WSA completely")

    def start_wsa(self):
        try:
            subprocess.Popen([str(self.wsa_client)])
            time.sleep(10)
            
            if not subprocess.run(["tasklist", "/FI", "IMAGENAME eq WsaClient.exe"], capture_output=True).returncode == 0:
                raise RuntimeError("Failed to start WSA")
        except Exception as e:
            logging.error(f"Error starting WSA: {e}")
            raise

    def switch_profile(self):
        try:
            if not self.check_admin():
                logging.error("This script requires administrator privileges")
                raise RuntimeError("Administrator privileges required")

            # Create profiles directory if it doesn't exist
            self.profiles_dir.mkdir(parents=True, exist_ok=True)

            # Update queue and get next profile
            self.update_queue()
            current_queue = self.read_queue()
            if not current_queue:
                raise RuntimeError("No profiles in queue")
            
            next_profile = current_queue[0]
            logging.info(f"Switching to profile: {next_profile}")
            
            # Setup profile files
            source_vhdx = self.profiles_dir / f"{next_profile}.vhdx"
            source_dat = self.profiles_dir / f"{next_profile}.dat"
            target_vhdx = self.wsa_base / "LocalCache/userdata.2.vhdx"
            target_dat = self.wsa_base / "Settings/settings.dat"
            
            if not source_vhdx.exists() or not source_dat.exists():
                raise RuntimeError(f"Profile files not found for {next_profile}")
            
            # Stop WSA and update files
            self.stop_wsa()
            
            # Remove existing files
            if target_vhdx.exists():
                target_vhdx.unlink()
            if target_dat.exists():
                target_dat.unlink()
            
            # Create symbolic link and copy file
            os.symlink(source_vhdx, target_vhdx)
            import shutil
            shutil.copy2(source_dat, target_dat)
            
            # Update queue
            current_queue.remove(next_profile)
            current_queue.append(next_profile)
            self.write_queue(current_queue)
            
            # Save current profile
            with open(self.current_profile, 'w', encoding='utf-8') as f:
                f.write(next_profile)
            
            # Start WSA and launch Google Photos
            self.start_wsa()
            self.launch_google_photos()
            
            # Send heartbeat to uptime monitoring
            try:
                requests.get("https://SUCCESS_URL.com")
                logging.info("Successfully sent heartbeat to uptime monitoring")
            except Exception as e:
                logging.warning(f"Failed to send heartbeat: {e}")
            
            logging.info("Success")
            
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            raise

    def launch_google_photos(self):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                subprocess.run([str(self.wsa_client), "/launch", "wsa://com.google.android.apps.photos"], 
                             capture_output=True)
                time.sleep(20)
                
                if subprocess.run(["tasklist", "/FI", "IMAGENAME eq WsaClient.exe"], 
                                capture_output=True).returncode == 0:
                    return
                
                if attempt < max_retries - 1:
                    time.sleep(5)
            except Exception as e:
                logging.warning(f"Error launching Google Photos: {e}")
                if attempt < max_retries - 1:
                    continue
                raise
        
        logging.warning(f"Failed to launch Google Photos after {max_retries} attempts")
        raise RuntimeError("Failed to launch Google Photos")

def main():
    try:
        switcher = WSAProfileSwitcher()
        switcher.switch_profile()
        with open(switcher.logfile, 'a', encoding='utf-8') as f:
            f.write('\n')
        sys.exit(0)
    except Exception as e:
        logging.error(f"Script failed: {e}")
        with open(switcher.logfile, 'a', encoding='utf-8') as f:
            f.write('\n')
        sys.exit(1)

if __name__ == "__main__":
    main() 

