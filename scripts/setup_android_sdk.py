import urllib.request
import zipfile
import os
import shutil

url = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"
dest = "cmdline-tools.zip"
sdk_dir = "C:/Users/ankes/OneDrive/Desktop/SIH/android-sdk"

print("Downloading Android commandlinetools...")
urllib.request.urlretrieve(url, dest)

print("Extracting...")
os.makedirs(f"{sdk_dir}/cmdline-tools", exist_ok=True)
with zipfile.ZipFile(dest, "r") as zip_ref:
    zip_ref.extractall(f"{sdk_dir}/cmdline-tools")

latest_dir = f"{sdk_dir}/cmdline-tools/latest"
if os.path.exists(latest_dir):
    shutil.rmtree(latest_dir)

os.rename(f"{sdk_dir}/cmdline-tools/cmdline-tools", latest_dir)

if os.path.exists(dest):
    os.remove(dest)

print("Android SDK cmdline-tools Ready at:", latest_dir)
